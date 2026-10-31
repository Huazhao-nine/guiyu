import CoreServices
import Foundation

struct WorkspaceIndexState {
    var phase = "starting"
    var indexed = 0
    var total = 0
    var chunks = 0
    var semantic = false
    var updated: Double = 0
    var skipped = 0
    var limited = false
    var message = "正在准备本地检索"
    var notes:[String] = []
    var active:Bool { ["starting","scanning","indexing"].contains(phase) }
    init() {}
    init(_ value:[String:Any]) {
        phase = value["phase"] as? String ?? "ready"; indexed = value["indexed"] as? Int ?? 0; total = value["total"] as? Int ?? 0; chunks = value["chunks"] as? Int ?? 0
        semantic = value["semantic"] as? Bool ?? false; updated = value["updated"] as? Double ?? 0; skipped = value["skipped_count"] as? Int ?? 0; limited = value["limited"] as? Bool ?? false
        message = value["message"] as? String ?? "工作区索引已就绪"
        notes = (value["skipped"] as? [[String:Any]] ?? []).map { ($0["name"] as? String ?? "资料")+"："+($0["reason"] as? String ?? "未读取") }
        if let count = value["truncated_count"] as? Int,count>0 { notes.append("\(count) 份长资料仅索引前 60,000 字符") }
        if limited { notes.append("当前工作区达到扫描范围，建议使用更具体的文件夹") }
    }
}
struct RetrievalEvidence:Codable {
    var query:String
    var scopeNote:String
    var indexed:Int
    var matched:Int
    var semantic:Bool
    var refreshed:Bool
    var hits:[RetrievalHit]
    init(_ value:[String:Any]) {
        query = value["query"] as? String ?? ""; scopeNote = value["scope_note"] as? String ?? ""; indexed = value["indexed_documents"] as? Int ?? 0; matched = value["matched_documents"] as? Int ?? 0
        semantic = value["semantic"] as? Bool ?? false; refreshed = value["refreshed"] as? Bool ?? false
        hits = (value["hits"] as? [[String:Any]] ?? []).map(RetrievalHit.init)
    }
}
struct RetrievalHit:Codable,Identifiable {
    var path:String
    var name:String
    var snippet:String
    var line:Int
    var reason:String
    var id:String { path+"-"+String(line) }
    init(_ value:[String:Any]) {
        path = value["path"] as? String ?? ""; name = value["name"] as? String ?? ""; snippet = value["snippet"] as? String ?? ""; line = value["line"] as? Int ?? 1; reason = value["reason"] as? String ?? "语义检索"
    }
}

final class WorkspaceMonitor {
    private var stream:FSEventStreamRef?
    private let changed:()->Void
    private let exclusions:[String]
    init(path:String,excluding:[String] = [],changed:@escaping()->Void) {
        self.changed = changed; self.exclusions = excluding
        var context = FSEventStreamContext(version:0,info:Unmanaged.passUnretained(self).toOpaque(),retain:nil,release:nil,copyDescription:nil)
        let callback:FSEventStreamCallback = { _,info,_,paths,_,_ in
            guard let info else { return }
            let monitor = Unmanaged<WorkspaceMonitor>.fromOpaque(info).takeUnretainedValue()
            let values = unsafeBitCast(paths,to:NSArray.self) as? [String] ?? []
            if !values.isEmpty && values.allSatisfy({ path in monitor.exclusions.contains { path == $0 || path.hasPrefix($0+"/") } }) { return }
            monitor.changed()
        }
        stream = FSEventStreamCreate(kCFAllocatorDefault,callback,&context,[path] as CFArray,FSEventStreamEventId(kFSEventStreamEventIdSinceNow),0.5,UInt32(kFSEventStreamCreateFlagFileEvents|kFSEventStreamCreateFlagWatchRoot|kFSEventStreamCreateFlagNoDefer|kFSEventStreamCreateFlagUseCFTypes))
        if let stream { FSEventStreamSetDispatchQueue(stream,DispatchQueue.main); if !FSEventStreamStart(stream) { FSEventStreamInvalidate(stream); FSEventStreamRelease(stream); self.stream = nil } }
    }
    func stop() { if let stream { FSEventStreamStop(stream);FSEventStreamInvalidate(stream);FSEventStreamRelease(stream);self.stream = nil } }
    deinit { stop() }
}
