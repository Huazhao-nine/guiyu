import Foundation
@main struct PrivacyScanChecks {
    @MainActor static func main() async throws {
        let directory=FileManager.default.temporaryDirectory.appendingPathComponent("guiyu-privacy-worker-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:directory) }
        let script=directory.appendingPathComponent("fixture.py")
        try "import json,sys,time\nr=json.loads(sys.stdin.readline())\ntime.sleep(r.get('delay',0))\nprint(json.dumps({'text':r['text']}))\n".write(to:script,atomically:true,encoding:.utf8)
        let python=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/GuiyuRuntime/python/bin/python")
        let worker=PrivacyScanWorker();var received=[String]()
        worker.start(data:Data("{\"text\":\"stale\",\"delay\":3}".utf8),python:python,script:script) { r in received.append(r?["text"] as? String ?? "error") }
        try await Task.sleep(nanoseconds:150_000_000)
        worker.start(data:Data("{\"text\":\"latest\"}".utf8),python:python,script:script) { r in received.append(r?["text"] as? String ?? "error") }
        for _ in 0..<50 { if !received.isEmpty { break };try await Task.sleep(nanoseconds:50_000_000) }
        precondition(received==["latest"],"Cancelled job must not deliver or block the next job")
        worker.start(data:Data("{\"text\":\"cancelled\",\"delay\":2}".utf8),python:python,script:script) { _ in received.append("unexpected") }
        worker.cancel();try await Task.sleep(nanoseconds:150_000_000)
        precondition(received==["latest"])
        print("PRIVACY_SCAN_CANCEL_AND_SERIAL_PASS")
    }
}
