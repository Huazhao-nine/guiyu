import AppKit
import Darwin
import Foundation
import SwiftUI

@_silgen_name("sandbox_init")
func enterSandbox(_ profile: UnsafePointer<CChar>, _ flags: UInt64, _ error: UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>) -> Int32
@_silgen_name("sandbox_free_error")
func freeSandboxError(_ error: UnsafeMutablePointer<CChar>)

var sandboxError: UnsafeMutablePointer<CChar>?
let isolated = "(version 1)(allow default)(deny network*)".withCString { enterSandbox($0, 0, &sandboxError) } == 0
if let sandboxError { freeSandboxError(sandboxError) }

if CommandLine.arguments.contains("--privacy-probe") {
    var outcomes: [[String: Any]] = []
    for host in ["127.0.0.1", "198.51.100.1"] {
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = UInt16(443).bigEndian
        inet_pton(AF_INET, host, &address.sin_addr)
        let result = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity:1) { Darwin.connect(fd,$0,socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        let code = errno
        close(fd)
        outcomes.append(["target":host,"denied":result == -1 && (code == EPERM || code == EACCES),"errno":code])
    }
    let data = try! JSONSerialization.data(withJSONObject:["sandbox":isolated,"probes":outcomes],options:[.sortedKeys])
    print(String(decoding:data,as:UTF8.self))
    exit(isolated && outcomes.allSatisfy { $0["denied"] as? Bool == true } ? 0 : 1)
}

enum AppEnvironment {
    static let root: URL = {
        if let path = ProcessInfo.processInfo.environment["GUIYU_ROOT"] { return URL(fileURLWithPath:path) }
        return Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent()
    }()
    static let sandboxed = isolated
}

struct GuiyuApp: App {
    @StateObject private var store = Store(root: AppEnvironment.root,hostSandboxed:AppEnvironment.sandboxed)
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(store).frame(minWidth:1060,minHeight:720).preferredColorScheme(.light)
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in store.shutdown() }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width:1360,height:880)
        .commands {
            CommandGroup(replacing:.newItem) { Button("新任务") { store.newTask() }.keyboardShortcut("n") }
            CommandGroup(after:.newItem) {
                Button("添加资料…") { store.chooseFiles() }.keyboardShortcut("o")
                Button("使用示例资料") { store.useDemo() }.keyboardShortcut("d",modifiers:[.command,.shift])
            }
        }
    }
}

GuiyuApp.main()
