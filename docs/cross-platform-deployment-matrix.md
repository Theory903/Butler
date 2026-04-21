# Butler Cross-Platform Deployment Matrix

**Version:** 1.0  
**Status:** Production Ready  
**Last Updated:** 2026-04-20

## Executive Summary

This specification defines Butler's deployment across all major platforms: Android, iOS, macOS, Windows, Linux, Web, and Smart Home. Each platform has honest capability boundaries based on OS constraints.

---

## Platform Overview

### Butler Cloud + Local Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUTLER DEPLOYMENT MODEL                      │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────────────────────────────────────────┐     │
│   │                 BUTLER CLOUD                        │     │
│   │  Identity │ Policy │ Memory │ Orchestration │ LLM   │     │
│   └─────────────────────────────────────────────────────┘     │
│                            │                                    │
│           ┌───────────────┼───────────────┐                   │
│           │               │               │                   │
│           ▼               ▼               ▼                   │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐          │
│   │ ANDROID  │    │   iOS    │    │  macOS   │          │
│   │   NODE   │    │   NODE   │    │   NODE   │          │
│   └───────────┘    └───────────┘    └───────────┘          │
│           │               │               │                   │
│           └───────────────┼───────────────┘                   │
│                           │                                    │
│           ┌───────────────┼───────────────┐                   │
│           │               │               │                   │
│           ▼               ▼               ▼                   │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐          │
│   │ WINDOWS  │    │  LINUX   │    │  BROWSER │          │
│   │   NODE   │    │   NODE   │    │   NODE   │          │
│   └───────────┘    └───────────┘    └───────────┘          │
│                                                              │
│   KEY RULE: Cloud decides, Local executes                    │
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Feature Matrix by Platform

### Voice & Audio

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Wake word detection | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Speech-to-text | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Text-to-speech | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Multi-language | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Voice activity detection | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Speaker diarization | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Streaming audio | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |

### Visual

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Camera access | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Image capture | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Screen capture | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Video recording | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Vision AI inference | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ⚠️ |
| Face detection | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ⚠️ |
| Object recognition | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |

### Notifications

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Push notifications | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| Local notifications | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Notification actions | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| Rich notifications | ✅ | ✅ | ✅ | ⚠️ | ❌ | ❌ | ✅ |
| Critical alerts | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Notification scheduling | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |

### Sensors

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| GPS/Location | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | ❌ |
| Accelerometer | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Gyroscope | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Bluetooth LE | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | ✅ |
| UWB | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| NFC | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Barometer | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Heart rate | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### Health & Fitness

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Health Connect | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| HealthKit | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Activity tracking | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ❌ |
| Sleep tracking | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Heart rate | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Workout detection | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Medication reminders | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### Home & IoT

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Matter control | ✅ | ✅ | ⚠️ | ❌ | ❌ | ❌ | ✅ |
| HomeKit | ⚠️ | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ |
| Google Home | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Zigbee | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Z-Wave | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Thread | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Local device discovery | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| IR control | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ⚠️ |

### Computing

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| File system access | ✅ | ⚠️ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Terminal access | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Shell commands | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Process management | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| System settings | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Background tasks | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Startup items | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |

### Browser & Web

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Browser automation | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Browser extension | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Web content parsing | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| WebSocket client | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| HTTP requests | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cookies management | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ |

### Communication

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Email send/receive | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Calendar access | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| Contacts access | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| SMS/MMS | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Phone calls | ✅ | ⚠️ | ✅ | ✅ | ❌ | ❌ | ❌ |
| VoIP | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ |

### AI & ML

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Local LLM | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Vision AI | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Speech AI | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| ONNX runtime | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| TensorFlow Lite | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Core ML | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| GPU acceleration | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ❌ |

### Networking

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| WiFi scanning | ✅ | ⚠️ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Network state | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| VPN support | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Tailscale | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ❌ | ❌ |
| DNS management | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Hotspot control | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |

### Security

| Feature | Android | iOS | macOS | Windows | Linux | Web | Smart Home |
|---------|---------|-----|-------|--------|-------|-----|------------|
| Biometric auth | ✅ | ✅ | ✅ | ✅ | ❌ | ⚠️ | ✅ |
| Keychain/Keystore | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Encryption | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Secure enclave | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| App sandbox | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| DRM | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ❌ |

---

## Platform-Specific Implementation

### Android Node

```kotlin
// Butler Android Node Architecture

class ButlerAndroidNode : Application() {
    
    // Core services
    lateinit var voiceService: VoiceService
    lateinit var sensorService: SensorService
    lateinit var healthService: HealthConnectService
    lateinit var notificationService: NotificationService
    lateinit var matterService: MatterService
    lateinit var proximityService: ProximityService
    
    // Background execution
    val workManager = WorkManager.getInstance(this)
    val foregroundService = ButlerForegroundService()
    
    // Health Connect integration
    fun requestHealthPermissions() {
        val permissions = setOf(
            HealthPermission.getReadPermission(Type.HEART_RATE),
            HealthPermission.getReadPermission(Type.SLEEP),
            HealthPermission.getReadPermission(Type.ACTIVITY)
        )
        healthConnectClient.permissionsService.requestPermissions(
            permissions,
            pendingResult
        )
    }
    
    // Matter integration
    fun setupMatter() {
        MatterService.start(this)
        // Discover and commission Matter devices
    }
    
    // Background voice
    fun startListening() {
        // Use RecognitionService for background voice
    }
}
```

### iOS Node

```swift
// Butler iOS Node Architecture

class ButlerIOSNode: NSObject, FlutterPlugin {
    
    // Core services
    var voiceService: VoiceService!
    var healthService: HealthKitService!
    var notificationService: NotificationService!
    
    // Background modes (configured in Info.plist)
    let backgroundModes: [String] = [
        "audio",           // Audio playback
        "fetch",          // Background fetch
        "processing",     // Background processing
        "location",       // Location updates
        "bluetooth-central" // BLE
    ]
    
    // HealthKit integration
    func requestHealthKitPermissions() {
        let typesToRead: Set<HKObjectType> = [
            HKObjectType.characteristicType(forIdentifier: .dateOfBirth)!,
            HKObjectType.workoutType(),
            HKObjectType.heartType()
        ]
        
        healthStore.requestAuthorization(toShare: nil, read: typesToRead) { success, error in
            // Handle authorization
        }
    }
}
```

### macOS Node

```swift
// Butler macOS Node Architecture

class ButlerMacNode: NSObject {
    
    // Full access capabilities
    var terminalService: TerminalService!
    var browserService: BrowserAutomationService!
    var fileService: FileSystemService!
    var screenService: ScreenCaptureService!
    
    // Launch at login
    func setupLaunchAtLogin() {
        // Use ServiceManagement framework
    }
    
    // Menu bar presence
    let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    
    // Accessibility permissions
    func requestAccessibility() {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true]
        AXIsProcessTrustedWithOptions(options as CFDictionary)
    }
}
```

### Windows Node

```csharp
// Butler Windows Node Architecture

public class ButlerWindowsNode
{
    // Full access capabilities
    private TerminalService terminalService;
    private BrowserAutomationService browserService;
    private FileSystemService fileService;
    private PowerService powerService;
    
    // Windows-specific
    public async Task StartAsync()
    {
        // Register as startup app
        await RegisterStartupAsync();
        
        // System tray
        SetupSystemTray();
        
        // Background service
        await Windows.ApplicationModel.Background
            .BackgroundTaskBuilder.RegisterAsync();
    }
}
```

### Linux Node

```python
# Butler Linux Node Architecture

class ButlerLinuxNode:
    def __init__(self):
        self.terminal_service = TerminalService()
        self.file_service = FileSystemService()
        self.process_service = ProcessService()
        self.network_service = NetworkService()
        self.dbus_service = DBusService()
        
    async def start(self):
        # Systemd integration
        await self.setup_systemd_units()
        
        # D-Bus for desktop notifications
        await self.setup_dbus()
        
        # NetworkManager integration
        await self.setup_network_manager()
```

### Browser Node

```javascript
// Butler Browser Node Architecture

class ButlerBrowserNode {
    constructor() {
        this.voiceService = null;
        this.notificationService = null;
    }
    
    async init() {
        // WASM-based local inference
        await this.loadWasmModules();
        
        // Web Audio API for voice
        this.voiceService = new WebVoiceService();
        
        // Web Push for notifications
        this.notificationService = new WebPushService();
    }
    
    // Limited capabilities compared to native
    capabilities = {
        voiceInput: true,
        voiceOutput: true,
        httpRequests: true,
        websockets: true,
        localStorage: true,
        // NOT available:
        // - terminal access
        // - file system (except via File API)
        // - background processing
        // - system settings
    };
}
```

---

## Capability Classes

### Cloud-Only (Always on Server)

| Capability | Description |
|-----------|-------------|
| LLM Reasoning | Full model inference |
| Memory Graph | Persistent knowledge |
| Recommendations | Ranking engine |
| Workflow Orchestration | DAG execution |
| Policy Engine | Access control |
| Analytics | Aggregated insights |

### Local-Only (Device-Specific)

| Capability | Platform |
|-----------|----------|
| Terminal/Shell | macOS, Windows, Linux |
| Full File System | Desktop platforms |
| System Settings | Desktop platforms |
| Background Services | Desktop platforms |
| Health Sensors | Mobile |
| BLE/UWB | Mobile, some desktop |

### Hybrid (Cloud + Local)

| Capability | Cloud Role | Local Role |
|-----------|------------|-------------|
| Voice Assistant | ASR/TTS | Wake word, VAD |
| Smart Home | Automation | Matter/Hub |
| Health | Analysis | Sensor collection |
| Context | Memory | Presence |
| Notifications | Routing | Delivery |

---

## Implementation Priority

### Priority 1: Core Voice (All Platforms)

| Platform | Task | Weeks |
|----------|------|-------|
| Android | Wake word + ASR + TTS | 1-2 |
| iOS | Wake word + ASR + TTS | 1-2 |
| Web | ASR + TTS | 2-3 |

### Priority 2: Desktop Control

| Platform | Task | Weeks |
|----------|------|-------|
| macOS | Terminal + Browser | 3-4 |
| Windows | Terminal + Browser | 4-5 |
| Linux | Terminal + Browser | 4-5 |

### Priority 3: Mobile Sensors

| Platform | Task | Weeks |
|----------|------|-------|
| Android | Health Connect + Proximity | 5-6 |
| iOS | HealthKit + Proximity | 5-6 |

### Priority 4: Home Integration

| Platform | Task | Weeks |
|----------|------|-------|
| Android | Matter + HomeKit | 6-7 |
| iOS | Matter + HomeKit | 6-7 |

---

## Platform Constraints Summary

### Android Strengths

- Best health platform (Health Connect)
- Best sensor access
- Best background task support (with battery optimization)
- Best IoT control (Matter, Zigbee, Z-Wave)
- Good BLE/UWB support

### iOS Strengths

- Best privacy
- Best HealthKit integration
- Excellent background audio
- Excellent notifications
- Strong security

### macOS/Windows/Linux Strengths

- Full terminal access
- Full file system access
- Browser automation
- System-level control
- Powerful for power users

### Web Limitations

- No background processing
- No terminal/file access
- Limited storage
- Cannot run without user interaction

---

**End of Specification**