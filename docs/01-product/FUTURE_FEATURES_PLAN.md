# Future Features Plan

## Overview

This document outlines planned features for future versions of Annie chatbot, beyond the V1 scope.

## V1.1: Web Interface

### Features

- **Web UI**: React/Next.js web interface
- **3D Avatar**: React Three Fiber implementation
- **Real-time Streaming**: SSE support
- **Mobile Responsive**: Mobile-friendly design

### Technical Decisions

- **Framework**: Next.js 14+ with React 18+
- **3D Library**: React Three Fiber
- **Styling**: Tailwind CSS
- **State Management**: React Context + SWR

### Timeline

- **Estimated**: 4-6 weeks after V1
- **Dependencies**: V1 backend API

## V1.2: iOS Native App

### Features

- **Native iOS App**: SwiftUI application
- **3D Avatar**: SceneKit implementation
- **Push Notifications**: User notifications
- **Offline Support**: Basic offline functionality

### Technical Decisions

- **Framework**: SwiftUI
- **3D Library**: SceneKit
- **Networking**: URLSession
- **Minimum iOS**: iOS 17+

### Timeline

- **Estimated**: 6-8 weeks after V1.1
- **Dependencies**: V1 backend API

## V2.0: Advanced Features

### Features

- **PostgreSQL Database**: Persistent storage for conversations, decisions, outcomes
- **Multi-Modality**: Image and voice understanding
- **WebSocket Support**: Bidirectional communication
- **Advanced Decision Frameworks**: Enhanced analysis and tracking
- **Advanced Gamification**: Unlockable features
- **Multi-Persona Support**: Multiple character modes

### Technical Decisions

- **Database**: PostgreSQL 16+ with Redis cache layer
- **Multi-Modality**: Vision models for images, Whisper for voice
- **WebSocket**: Native WebSocket support
- **Gamification**: Enhanced affection system

### Timeline

- **Estimated**: 8-10 weeks after V1.2
- **Dependencies**: V1.1 and V1.2

## V2.1: A2A Protocol Integration

### Features

- **A2A Adapter**: A2A protocol support
- **Claude Integration**: Claude can use Annie
- **Gemini Integration**: Gemini can use Annie
- **Agent Registry**: Register with A2A registry

### Technical Decisions

- **Protocol**: A2A protocol (when mature)
- **Adapter Pattern**: A2A adapter layer
- **Registry**: Google A2A registry

### Timeline

- **Estimated**: 4-6 weeks after V2.0
- **Dependencies**: A2A protocol maturity
- **Status**: Deferred until protocol is stable

### Implementation Notes

- Monitor A2A protocol development
- Design adapter layer in advance
- Prepare capability registration
- Test with Claude/Gemini when available

## V3.0: Advanced AI Features

### Features

- **Fine-tuning**: Character-specific fine-tuning
- **Advanced Memory**: Enhanced memory capabilities
- **Personalization**: Deep personalization
- **Voice Interaction**: STT and TTS (moved from V2.0)

### Timeline

- **Estimated**: 12+ weeks after V2.1
- **Dependencies**: Previous versions

## Feature Prioritization

### High Priority

1. Web Interface (V1.1)
2. iOS App (V1.2)
3. PostgreSQL Database (V2.0)
4. Multi-Modality (V2.0)
5. WebSocket Support (V2.0)

### Medium Priority

6. Voice Interaction (V3.0)
7. Advanced Gamification (V2.0)
8. A2A Protocol (V2.1)

### Low Priority

9. Fine-tuning (V3.0)
10. Advanced Personalization (V3.0)

## References

- [Product Requirements](./PRODUCT_REQUIREMENTS.md) - Product vision and goals
- [V1 Implementation Plan](../04-implementation/V1_IMPLEMENTATION_PLAN.md) - Current implementation
- [Architecture Plan](../02-architecture/ARCHITECTURE_PLAN.md) - System architecture
- [Research Summary](../06-reference/RESEARCH_SUMMARY.md) - Technical research details

