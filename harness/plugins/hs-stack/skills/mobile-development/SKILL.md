---
name: hs-stack:mobile-development
description: Build mobile apps with React Native, Flutter, Swift/SwiftUI, Kotlin/Jetpack Compose. Use for iOS/Android, mobile UX, performance optimization, offline-first, app store deployment.
user-invocable: true
when_to_use: "Invoke when the target is an iOS or Android app."
category: frameworks
keywords: [react-native, flutter, swift, kotlin, ios]
license: MIT
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, WebFetch]
argument-hint: "[platform] [feature]"
metadata:
  owner: harness
  compliance-tier: knowledge
---

# Mobile Development Skill

Production-ready mobile development with modern frameworks, best practices, and mobile-first thinking patterns.

## When to Use

- Building mobile applications (iOS, Android, or cross-platform)
- Implementing mobile-first design and UX patterns
- Optimizing for mobile constraints (battery, memory, network, small screens)
- Making native vs cross-platform technology decisions
- Implementing offline-first architecture and data sync
- Following platform-specific guidelines (iOS HIG, Material Design)
- Optimizing mobile app performance and user experience
- Implementing mobile security and authentication
- Testing mobile applications (unit, integration, E2E)
- Deploying to App Store and Google Play

## Technology Selection Guide

**Cross-Platform Frameworks:**
- **React Native**: JavaScript expertise, web code sharing, mature ecosystem (121K stars, 67% familiarity)
- **Flutter**: Performance-critical apps, complex animations, fastest-growing (170K stars, 46% adoption)

**Native Development:**
- **iOS (Swift/SwiftUI)**: Maximum iOS performance, latest features, Apple ecosystem integration
- **Android (Kotlin/Jetpack Compose)**: Maximum Android performance, Material Design 3, platform optimization

See: `references/mobile-frameworks.md` for detailed framework comparisons

## Mobile Development Mindset

**The 10 Commandments of Mobile Development:**

1. **Performance is Foundation, Not Feature** - 70% abandon apps >3s load time
2. **Every Kilobyte, Every Millisecond Matters** - Mobile constraints are real
3. **Offline-First by Default** - Network is unreliable, design for it
4. **User Context > Developer Environment** - Think real-world usage scenarios
5. **Platform Awareness Without Platform Lock-In** - Respect platform conventions
6. **Iterate, Don't Perfect** - Ship, measure, improve cycle is survival
7. **Security and Accessibility by Design** - Not afterthoughts
8. **Test on Real Devices** - Simulators lie about performance
9. **Architecture Scales with Complexity** - Don't over-engineer simple apps
10. **Continuous Learning is Survival** - Mobile landscape evolves rapidly

See: `references/mobile-mindset.md` for thinking patterns and decision frameworks

## Reference Navigation

**Core Technologies:**
- `mobile-frameworks.md` - React Native, Flutter, Swift, Kotlin, framework comparison matrices, when to use each
- `mobile-ios.md` - Swift 6, SwiftUI, iOS architecture patterns, HIG, App Store requirements, platform capabilities
- `mobile-android.md` - Kotlin, Jetpack Compose, Material Design 3, Play Store, Android-specific features

**Best Practices & Development Mindset:**
- `mobile-best-practices.md` - Mobile-first design, performance optimization, offline-first architecture, security, testing, accessibility, deployment, analytics
- `mobile-debugging.md` - Debugging tools, performance profiling, crash analysis, network debugging, platform-specific debugging
- `mobile-mindset.md` - Thinking patterns, decision frameworks, platform-specific thinking, common pitfalls, debugging strategies
- `mobile-playbook.md` - Performance targets, architecture/security/testing/deployment practices, decision matrices, framework comparison, implementation checklist, platform guidelines, pitfalls, budgets


## Quick Playbook

Performance targets, architecture/security/testing/deployment best practices, decision
matrices, framework comparison, implementation checklist, platform-specific guidelines,
common pitfalls, and performance budgets: `references/mobile-playbook.md`.

## Resources

**Official Documentation:**
- React Native: https://reactnative.dev/
- Flutter: https://flutter.dev/
- iOS HIG: https://developer.apple.com/design/human-interface-guidelines/
- Material Design: https://m3.material.io/
- OWASP Mobile: https://owasp.org/www-project-mobile-top-10/

**Tools & Testing:**
- Detox E2E: https://wix.github.io/Detox/
- Appium: https://appium.io/
- Fastlane: https://fastlane.tools/
- Firebase: https://firebase.google.com/

**Community:**
- React Native Directory: https://reactnative.directory/
- Pub.dev (Flutter packages): https://pub.dev/
- Awesome React Native: https://github.com/jondot/awesome-react-native
- Awesome Flutter: https://github.com/Solido/awesome-flutter
