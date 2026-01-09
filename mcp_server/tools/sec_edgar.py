"""
SEC Edgar Filing Tools

Provides tools for fetching SEC filings (10-K, 10-Q, 8-K) from the
SEC EDGAR database. Useful for deep fundamental analysis with access
to official regulatory filings.

SEC EDGAR API is free and requires no authentication, but requires
a User-Agent header with contact info.
"""

import json
import re
import time
from typing import Any, Dict, List, Optional

import httpx
import redis.asyncio as redis

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)

# Cache TTL for SEC filings: 7 days (604800 seconds)
# SEC filings are immutable once filed
SEC_FILINGS_CACHE_TTL = 604800

# SEC EDGAR API base URLs
SEC_DATA_URL = "https://data.sec.gov"  # For filings and submissions
SEC_WWW_URL = "https://www.sec.gov"    # For company tickers lookup

# Required User-Agent for SEC API (they require identification)
SEC_USER_AGENT = "Annie-AI-Assistant/1.0 (contact@example.com)"

# Common 10-K sections and their item numbers
TEN_K_SECTIONS = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Common Equity",
    "6": "Selected Financial Data",
    "7": "MD&A (Management Discussion & Analysis)",
    "7A": "Quantitative & Qualitative Disclosures About Market Risk",
    "8": "Financial Statements",
    "9": "Changes in Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "10": "Directors & Executive Officers",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Related Party Transactions",
    "14": "Principal Accountant Fees",
}


def _get_redis_client() -> Optional[redis.Redis]:
    """Create Redis client for caching."""
    try:
        config = get_config()
        redis_host = config.get("REDIS_HOST", "redis")
        redis_port = int(config.get("REDIS_PORT", 6379))
        return redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
    except Exception as e:
        logger.warning(f"Failed to create Redis client: {e}")
        return None


async def _get_cik_from_ticker(ticker: str) -> Optional[str]:
    """
    Get CIK (Central Index Key) from ticker symbol.

    SEC uses CIK as the primary identifier, not ticker symbols.
    We use the SEC's company_tickers.json to map ticker -> CIK.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SEC_WWW_URL}/files/company_tickers.json",
                headers={"User-Agent": SEC_USER_AGENT}
            )
            response.raise_for_status()

            data = response.json()
            ticker_upper = ticker.upper()

            # company_tickers.json format: {"0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc"}, ...}
            for entry in data.values():
                if entry.get("ticker") == ticker_upper:
                    # CIK needs to be zero-padded to 10 digits
                    cik = str(entry.get("cik_str", ""))
                    return cik.zfill(10)

            logger.warning(f"CIK not found for ticker: {ticker}")
            return None

    except Exception as e:
        logger.error(f"Failed to get CIK for {ticker}: {e}")
        return None


async def _get_company_filings(cik: str) -> Optional[Dict[str, Any]]:
    """
    Get company filing metadata from SEC EDGAR.

    Returns filing history including accession numbers needed to fetch full filings.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{SEC_DATA_URL}/submissions/CIK{cik}.json",
                headers={"User-Agent": SEC_USER_AGENT}
            )
            response.raise_for_status()
            return response.json()

    except Exception as e:
        logger.error(f"Failed to get company filings for CIK {cik}: {e}")
        return None


async def _fetch_filing_document(accession_number: str, cik: str, primary_doc: str) -> Optional[str]:
    """
    Fetch the primary document text from a filing.

    Args:
        accession_number: Filing accession number (e.g., "0000320193-24-000123")
        cik: Company CIK (zero-padded)
        primary_doc: Primary document filename (e.g., "aapl-20240928.htm")

    Returns:
        Document text content or None on failure
    """
    try:
        # Format accession number for URL (remove dashes)
        accession_no_dashes = accession_number.replace("-", "")
        # Archives URL uses CIK without leading zeros
        cik_no_padding = cik.lstrip("0") or "0"

        url = f"{SEC_WWW_URL}/Archives/edgar/data/{cik_no_padding}/{accession_no_dashes}/{primary_doc}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": SEC_USER_AGENT}
            )
            response.raise_for_status()
            return response.text

    except Exception as e:
        logger.warning(f"Failed to fetch filing document: {e}")
        return None


def _extract_section_from_10k(html_content: str, section: str, max_length: int = 15000) -> Optional[str]:
    """
    Extract a specific section from a 10-K filing.

    This extraction handles Table of Contents by finding the actual section
    (identified by having substantial content after the header).

    Args:
        html_content: Raw HTML content of the 10-K filing
        section: Section number (e.g., "1A" for Risk Factors)
        max_length: Maximum characters to return

    Returns:
        Extracted section text or None if not found
    """
    try:
        # Remove HTML tags for text extraction
        text = re.sub(r'<[^>]+>', ' ', html_content)
        text = re.sub(r'\s+', ' ', text)

        # Look for section markers like "Item 1A" or "ITEM 1A"
        section_pattern = rf"Item\s*{section}[\.\s\-:]"

        # Find ALL matches - we need to skip TOC entries
        matches = list(re.finditer(section_pattern, text, re.IGNORECASE))
        if not matches:
            return None

        # For each match, find content until next Item marker
        # Choose the match with the most content (skip short TOC references)
        best_section = None
        best_length = 0
        min_content_length = 500  # Minimum chars to consider it a real section

        for match in matches:
            remaining_text = text[match.end():]
            next_item_match = re.search(r"Item\s*\d+[A-B]?[\.\s\-:]", remaining_text, re.IGNORECASE)

            if next_item_match:
                section_content = remaining_text[:next_item_match.start()].strip()
            else:
                # No next item found, take up to max_length
                section_content = remaining_text[:max_length].strip()

            content_length = len(section_content)

            # Only consider sections with substantial content
            if content_length >= min_content_length and content_length > best_length:
                best_length = content_length
                # Include the header
                header_text = text[match.start():match.end()]
                best_section = header_text + section_content

        if not best_section:
            # Fall back to first match if no substantial content found
            match = matches[0]
            remaining_text = text[match.end():]
            next_item_match = re.search(r"Item\s*\d+[A-B]?[\.\s\-:]", remaining_text, re.IGNORECASE)
            if next_item_match:
                best_section = text[match.start():match.end() + next_item_match.start()].strip()
            else:
                best_section = text[match.start():match.start() + max_length].strip()

        # Truncate if too long
        if len(best_section) > max_length:
            best_section = best_section[:max_length] + "... [truncated]"

        return best_section

    except Exception as e:
        logger.warning(f"Failed to extract section {section}: {e}")
        return None


async def get_sec_filings_tool_handler(
    ticker: str,
    filing_type: str = "10-K",
    limit: int = 3,
    include_text: bool = False,
    sections: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Fetch SEC filings for a company.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        filing_type: Type of filing - '10-K', '10-Q', '8-K', or 'all'
        limit: Number of filings to return (max 10)
        include_text: Whether to fetch full text (slower, larger response)
        sections: For 10-K, specific sections to extract (e.g., ['1A', '7'])

    Returns:
        dict: Filing metadata and optionally extracted text
    """
    start_time = time.time()

    # Normalize inputs
    ticker = ticker.upper().strip()
    filing_type = filing_type.upper().strip()
    limit = min(max(1, limit), 10)  # Clamp to 1-10

    # Validate filing type
    valid_types = ["10-K", "10-Q", "8-K", "ALL"]
    if filing_type not in valid_types:
        return {
            "status": "error",
            "message": f"Invalid filing_type: '{filing_type}'. Must be one of: {', '.join(valid_types)}"
        }

    logger.info(
        "Fetching SEC filings",
        extra={
            "ticker": ticker,
            "filing_type": filing_type,
            "limit": limit,
            "include_text": include_text
        }
    )

    # Check cache first (only for metadata, not full text)
    cache_key = f"sec_filings:{ticker}:{filing_type}:{limit}"
    redis_client = None

    if not include_text:  # Only cache metadata requests
        try:
            redis_client = _get_redis_client()
            if redis_client:
                cached_json = await redis_client.get(cache_key)
                if cached_json:
                    cached_data = json.loads(cached_json)
                    cached_data["from_cache"] = True
                    cached_data["duration_ms"] = int((time.time() - start_time) * 1000)
                    logger.info("SEC filings cache hit", extra={"ticker": ticker})
                    await redis_client.close()
                    return cached_data
        except Exception as e:
            logger.warning(f"Redis cache check failed: {e}")

    try:
        # Step 1: Get CIK from ticker
        cik = await _get_cik_from_ticker(ticker)
        if not cik:
            duration_ms = int((time.time() - start_time) * 1000)
            if redis_client:
                await redis_client.close()
            return {
                "status": "error",
                "message": f"Could not find SEC CIK for ticker '{ticker}'. The company may not file with SEC.",
                "ticker": ticker,
                "duration_ms": duration_ms
            }

        logger.debug(f"Found CIK {cik} for {ticker}")

        # Step 2: Get company filing metadata
        company_data = await _get_company_filings(cik)
        if not company_data:
            duration_ms = int((time.time() - start_time) * 1000)
            if redis_client:
                await redis_client.close()
            return {
                "status": "error",
                "message": f"Failed to retrieve SEC filings for '{ticker}'.",
                "ticker": ticker,
                "cik": cik,
                "duration_ms": duration_ms
            }

        # Build result
        result = {
            "status": "success",
            "ticker": ticker,
            "cik": cik,
            "company_name": company_data.get("name"),
            "sic": company_data.get("sic"),
            "sic_description": company_data.get("sicDescription"),
            "filings": [],
            "from_cache": False
        }

        # Step 3: Extract relevant filings
        recent_filings = company_data.get("filings", {}).get("recent", {})

        if not recent_filings:
            logger.warning(f"No recent filings found for {ticker}")
            result["message"] = "No recent filings available"
            return result

        # Get filing arrays
        forms = recent_filings.get("form", [])
        filing_dates = recent_filings.get("filingDate", [])
        accession_numbers = recent_filings.get("accessionNumber", [])
        primary_docs = recent_filings.get("primaryDocument", [])
        descriptions = recent_filings.get("primaryDocDescription", [])
        report_dates = recent_filings.get("reportDate", [])

        # Filter by filing type
        filing_count = 0
        for i in range(len(forms)):
            if filing_count >= limit:
                break

            form = forms[i] if i < len(forms) else None

            # Check if this filing matches requested type
            if filing_type != "ALL" and form != filing_type:
                continue

            filing_info = {
                "type": form,
                "filed_date": filing_dates[i] if i < len(filing_dates) else None,
                "report_date": report_dates[i] if i < len(report_dates) else None,
                "accession_number": accession_numbers[i] if i < len(accession_numbers) else None,
                "primary_document": primary_docs[i] if i < len(primary_docs) else None,
                "description": descriptions[i] if i < len(descriptions) else None,
            }

            # Build SEC URL (CIK without leading zeros in Archives path)
            if filing_info["accession_number"]:
                acc_no_dashes = filing_info["accession_number"].replace("-", "")
                cik_for_url = cik.lstrip("0") or "0"
                filing_info["url"] = f"https://www.sec.gov/Archives/edgar/data/{cik_for_url}/{acc_no_dashes}/{filing_info['primary_document']}"
                filing_info["index_url"] = f"https://www.sec.gov/Archives/edgar/data/{cik_for_url}/{acc_no_dashes}/"

            # Step 4: Optionally fetch full text and extract sections
            if include_text and filing_info["accession_number"] and filing_info["primary_document"]:
                logger.debug(f"Fetching full text for {form} filed {filing_info['filed_date']}")

                full_text = await _fetch_filing_document(
                    filing_info["accession_number"],
                    cik,
                    filing_info["primary_document"]
                )

                if full_text:
                    # For 10-K, extract specific sections if requested
                    if form == "10-K" and sections:
                        filing_info["sections"] = {}
                        for section in sections:
                            section_upper = section.upper()
                            section_text = _extract_section_from_10k(full_text, section_upper)
                            if section_text:
                                section_name = TEN_K_SECTIONS.get(section_upper, f"Item {section_upper}")
                                filing_info["sections"][f"item_{section_upper}"] = {
                                    "name": section_name,
                                    "text": section_text
                                }
                    else:
                        # Return truncated full text
                        max_text_length = 20000
                        if len(full_text) > max_text_length:
                            filing_info["text"] = full_text[:max_text_length] + "... [truncated]"
                            filing_info["text_truncated"] = True
                        else:
                            filing_info["text"] = full_text
                            filing_info["text_truncated"] = False

            result["filings"].append(filing_info)
            filing_count += 1

        duration_ms = int((time.time() - start_time) * 1000)
        result["duration_ms"] = duration_ms
        result["filing_count"] = len(result["filings"])

        # Cache the result (only if not including full text)
        if not include_text and redis_client:
            try:
                await redis_client.setex(
                    cache_key,
                    SEC_FILINGS_CACHE_TTL,
                    json.dumps(result)
                )
                logger.info(
                    "SEC filings cached",
                    extra={"ticker": ticker, "cache_key": cache_key}
                )
            except Exception as e:
                logger.warning(f"Failed to cache SEC filings: {e}")

        logger.info(
            "SEC filings retrieved",
            extra={
                "ticker": ticker,
                "filing_count": len(result["filings"]),
                "duration_ms": duration_ms
            }
        )

        return result

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Error fetching SEC filings",
            extra={"ticker": ticker, "error": str(e), "duration_ms": duration_ms},
            exc_info=True
        )
        return {
            "status": "error",
            "message": f"Failed to fetch SEC filings: {str(e)}",
            "ticker": ticker,
            "duration_ms": duration_ms
        }
    finally:
        if redis_client:
            try:
                await redis_client.close()
            except Exception:
                pass


# SEC filings tool definition
get_sec_filings_tool = {
    "name": "get_sec_filings",
    "description": (
        "Fetch SEC EDGAR filings (10-K, 10-Q, 8-K) for a company. "
        "10-K is the annual report with comprehensive business info, risk factors, and financials. "
        "10-Q is quarterly report. 8-K is material events. "
        "Use this for deep due diligence, reading risk factors, or understanding business details "
        "not available in standard financial data. Can extract specific 10-K sections like "
        "Risk Factors (1A) or MD&A (7)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Stock ticker symbol (e.g., 'AAPL', 'GOOGL', 'TSLA')"
            },
            "filing_type": {
                "type": "string",
                "description": "Type of SEC filing: '10-K' (annual), '10-Q' (quarterly), '8-K' (events), or 'all'. Default: 10-K",
                "enum": ["10-K", "10-Q", "8-K", "all"],
                "default": "10-K"
            },
            "limit": {
                "type": "integer",
                "description": "Number of filings to return (1-10). Default: 3",
                "minimum": 1,
                "maximum": 10,
                "default": 3
            },
            "include_text": {
                "type": "boolean",
                "description": "Fetch full filing text (slower, larger response). Default: false",
                "default": False
            },
            "sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For 10-K filings, specific sections to extract: '1' (Business), '1A' (Risk Factors), '7' (MD&A), '7A' (Market Risk), '8' (Financial Statements). Only used if include_text=true."
            }
        },
        "required": ["ticker"]
    },
    "handler": get_sec_filings_tool_handler
}
