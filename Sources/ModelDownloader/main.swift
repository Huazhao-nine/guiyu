// A LaunchServices application: it never receives prompts, source paths or history.
import AppKit
import CryptoKit
import Darwin
import Foundation

@_silgen_name("sandbox_init")
func sandboxInit(_ profile: UnsafePointer<CChar>, _ flags: UInt64, _ error: UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>) -> Int32
@_silgen_name("sandbox_free_error")
func sandboxFree(_ error: UnsafeMutablePointer<CChar>)

let fm = FileManager.default
let root = ModelStorage.root
func safeDirectory(_ url:URL) throws {
    for component in [url] + Array(sequence(first:url.deletingLastPathComponent(),next: { $0.path == "/" ? nil : $0.deletingLastPathComponent() })) {
        if (try? component.resourceValues(forKeys:[.isSymbolicLinkKey]).isSymbolicLink) == true { throw NSError(domain:"GuiyuDownload",code:1) }
    }
    try fm.createDirectory(at:url,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
}
try safeDirectory(root)
func quoted(_ path:String)->String { "\""+path.replacingOccurrences(of:"\\",with:"\\\\").replacingOccurrences(of:"\"",with:"\\\"")+"\"" }
// Allow public OS resources, the signed catalog and the dedicated model store.
// No access to home documents, app history, workspaces, credentials or mounted volumes.
let readable = ["/System","/usr","/Library/Apple","/Library/Preferences","/Library/Keychains","/private/etc","/private/var/db","/dev",Bundle.main.bundleURL.path,root.path]
let profile = "(version 1)(allow default)(deny file-read-data)(deny file-write*)(allow file-read-data " + readable.map { "(subpath \(quoted($0)))" }.joined(separator:" ") + ")(allow file-write* (subpath \(quoted(root.path))))(deny process-exec*)"
var failure: UnsafeMutablePointer<CChar>?
let isolated = profile.withCString { sandboxInit($0,0,&failure) } == 0
if let failure { sandboxFree(failure) }
guard isolated else { exit(73) }
let lockFD = open(root.appendingPathComponent("service.lock").path,O_CREAT|O_RDWR|O_NOFOLLOW,0o600)
guard lockFD >= 0, flock(lockFD,LOCK_EX|LOCK_NB) == 0 else { exit(0) }

struct Command: Codable { var id:String; var action:String; var modelID:String }
final class Downloader: NSObject, URLSessionDataDelegate {
    let models = CatalogModel.load()
    var model: CatalogModel?
    var index = 0
    var done: Int64 = 0
    var received: Int64 = 0
    var offset: Int64 = 0
    var handle: FileHandle?
    var task: URLSessionDataTask?
    var session: URLSession!
    var status: ModelDownloadStatus?
    var lastWrite = Date.distantPast
    var idle = Date()
    var generation = UUID()
    var tick: Timer?
    var activity: NSObjectProtocol?
    var stage: URL { root.appendingPathComponent("Partial/"+model!.id,isDirectory:true) }
    override init() {
        super.init()
        let config = URLSessionConfiguration.ephemeral
        config.httpCookieStorage = nil; config.urlCredentialStorage = nil; config.urlCache = nil
        config.httpShouldSetCookies = false; config.connectionProxyDictionary = [:]
        config.timeoutIntervalForRequest = 35; config.timeoutIntervalForResource = 7200
        session = URLSession(configuration:config,delegate:self,delegateQueue:OperationQueue.main)
    }
    func update(_ phase:String,_ message:String,force:Bool = true) {
        guard let model else { return }
        if !force && Date().timeIntervalSince(lastWrite)<0.3 { return }
        status = ModelDownloadStatus(modelID:model.id,phase:phase,completed:done+received,total:model.bytes,detail:message)
        try? ModelStorage.write(status!,to:ModelStorage.status(model.id)); lastWrite = Date()
    }
    func cleanup() {
        try? handle?.close(); handle = nil; task = nil
        if let activity { ProcessInfo.processInfo.endActivity(activity) }; activity = nil
        generation = UUID(); model = nil; idle = Date()
    }
    func fail(_ text:String) { update("failed",text); cleanup() }
    func poll() {
        let commandURL = root.appendingPathComponent("command.json")
        if let data = try? Data(contentsOf:commandURL), data.count < 1024, let cmd = try? JSONDecoder().decode(Command.self,from:data) {
            try? fm.removeItem(at:commandURL)
            if cmd.action == "pause", model?.id == cmd.modelID {
                task?.cancel(); task = nil
                try? handle?.synchronize(); update("paused","已暂停，已下载的内容会保留"); cleanup()
            } else if cmd.action == "pause", model == nil, let chosen = models.first(where:{$0.id == cmd.modelID}) {
                let previous = (try? Data(contentsOf:ModelStorage.status(chosen.id))).flatMap { try? JSONDecoder().decode(ModelDownloadStatus.self,from:$0) }
                try? ModelStorage.write(ModelDownloadStatus(modelID:chosen.id,phase:"paused",completed:previous?.completed ?? 0,total:chosen.bytes,detail:"已暂停，点击继续即可下载"),to:ModelStorage.status(chosen.id))
                idle = Date()
            } else if cmd.action == "download", model == nil, let chosen = models.first(where:{$0.id == cmd.modelID}) {
                model = chosen; index = 0; done = 0; received = 0
                activity = ProcessInfo.processInfo.beginActivity(options:.userInitiatedAllowingIdleSystemSleep,reason:"正在下载用户选择的本地模型")
                update("starting","正在连接模型源…")
                do {
                    try safeDirectory(stage)
                    let attributes = try fm.attributesOfFileSystem(forPath:root.path)
                    let free = (attributes[.systemFreeSize] as? NSNumber)?.int64Value ?? 0
                    let cached = chosen.files.reduce(Int64(0)) { $0 + min($1.bytes,((try? fm.attributesOfItem(atPath:stage.appendingPathComponent($1.name+".part").path)[.size]) as? NSNumber)?.int64Value ?? 0) }
                    guard free > chosen.bytes-cached+512*1024*1024 else { fail("可用磁盘空间不足，请释放空间后重试。"); return }
                    next()
                } catch { fail("模型目录暂时无法写入，请检查磁盘。") }
            }
        }
        if let current = status, current.active, Date().timeIntervalSince(lastWrite)>2 { update(current.phase,current.detail) }
        if model == nil && Date().timeIntervalSince(idle)>90 { exit(0) }
    }
    func next() {
        guard let model else { return }
        guard index < model.files.count else { install(); return }
        let file = model.files[index]
        guard file.name.range(of:"^[A-Za-z0-9_.-]+$",options:.regularExpression) != nil else { fail("模型清单无效。"); return }
        let url = stage.appendingPathComponent(file.name+".part")
        do {
            guard (try? url.resourceValues(forKeys:[.isSymbolicLinkKey]).isSymbolicLink) != true else { fail("模型目录包含链接，已停止下载。"); return }
            let completedURL = stage.appendingPathComponent(file.name)
            if fm.fileExists(atPath:completedURL.path),!fm.fileExists(atPath:url.path) { try fm.moveItem(at:completedURL,to:url) }
            offset = ((try? fm.attributesOfItem(atPath:url.path)[.size]) as? NSNumber)?.int64Value ?? 0
            if offset == file.bytes { received = offset; verify(); return }
            if offset > file.bytes { try fm.removeItem(at:url); offset = 0 }
            let fd = open(url.path,O_WRONLY|O_CREAT|O_NOFOLLOW,0o600)
            guard fd>=0 else { throw POSIXError(POSIXErrorCode(rawValue:errno) ?? .EIO) }
            handle = FileHandle(fileDescriptor:fd,closeOnDealloc:true); try handle?.seekToEnd(); received = offset
            guard let remote=file.downloadURL(repository:model.repository,revision:model.revision) else { fail("组件下载清单无效。");return }
            var request = URLRequest(url:remote); request.httpMethod = "GET"
            request.setValue("identity",forHTTPHeaderField:"Accept-Encoding")
            request.setValue("Guiyu-Model-Downloader/0.4",forHTTPHeaderField:"User-Agent")
            if offset>0 { request.setValue("bytes=\(offset)-",forHTTPHeaderField:"Range") }
            task = session.dataTask(with:request)
            update("downloading","正在下载 \(file.name)"); task!.resume()
        } catch { fail("下载文件无法写入（\((error as NSError).code)），请检查磁盘后重试。") }
    }
    func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive response:URLResponse,completionHandler:@escaping(URLSession.ResponseDisposition)->Void) {
        guard dataTask === task, let model, let http = response as? HTTPURLResponse else { completionHandler(.cancel); return }
        let file = model.files[index]
        if http.statusCode == 200 {
            if offset>0 { try? handle?.truncate(atOffset:0); try? handle?.seek(toOffset:0); offset = 0; received = 0 }
        } else if http.statusCode == 206 {
            let range = http.value(forHTTPHeaderField:"Content-Range") ?? ""
            guard range.hasPrefix("bytes \(offset)-"),range.hasSuffix("/\(file.bytes)") else { completionHandler(.cancel); fail("模型源返回了不匹配的续传范围，请重试。"); return }
        } else { completionHandler(.cancel); fail("模型源暂时不可用（\(http.statusCode)），请稍后重试。"); return }
        completionHandler(.allow)
    }
    func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive data:Data) {
        guard dataTask === task, let model else { return }
        guard received+Int64(data.count)<=model.files[index].bytes else { dataTask.cancel(); fail("下载大小与固定清单不一致，已停止。"); return }
        do { try handle?.write(contentsOf:data); received += Int64(data.count); update("downloading","正在下载 \(model.files[index].name)",force:false) }
        catch { dataTask.cancel(); fail("磁盘写入失败，已保留下载进度。") }
    }
    func urlSession(_ session:URLSession,task completedTask:URLSessionTask,didCompleteWithError error:Error?) {
        guard completedTask === task, model != nil else { return }
        try? handle?.synchronize(); try? handle?.close(); handle = nil; task = nil
        if error != nil { fail("连接中断，请点击重试；已下载的内容会继续使用。"); return }
        verify()
    }
    func verify() {
        guard let model else { return }
        let generation = self.generation
        let file = model.files[index], url = stage.appendingPathComponent(file.name+".part")
        update("verifying","正在校验 \(file.name)…")
        // Hash off the UI/polling queue so pausing remains responsive for large weights.
        DispatchQueue.global(qos:.utility).async {
            var hash = SHA256(), count:Int64 = 0
            do {
                let reader = try FileHandle(forReadingFrom:url); defer { try? reader.close() }
                while let chunk = try reader.read(upToCount:1024*1024),!chunk.isEmpty { hash.update(data:chunk); count += Int64(chunk.count) }
                let digest = hash.finalize().map { String(format:"%02x",$0) }.joined()
                DispatchQueue.main.async {
                    guard self.generation == generation, self.model?.id == model.id, self.index < model.files.count, model.files[self.index].name == file.name else { return }
                    if digest != file.sha256 || count != file.bytes {
                        try? fm.removeItem(at:url); self.received = 0; self.fail("文件校验未通过，已移除损坏分片。请重试。"); return
                    }
                    self.done += file.bytes; self.received = 0; self.index += 1; self.next()
                }
            } catch { DispatchQueue.main.async { if self.generation == generation, self.model?.id == model.id { self.fail("校验文件时遇到问题，请重试。") } } }
        }
    }
    func install() {
        guard let model else { return }
        do {
            let destination = ModelStorage.installed(model.id)
            try safeDirectory(destination.deletingLastPathComponent())
            guard !fm.fileExists(atPath:destination.path) else { fail("该模型目录已经存在，请在模型库检查后重试。"); return }
            for file in model.files { try fm.moveItem(at:stage.appendingPathComponent(file.name+".part"),to:stage.appendingPathComponent(file.name)) }
            try ModelStorage.write(["revision":model.revision,"repository":model.repository],to:stage.appendingPathComponent("guiyu-install.json"))
            try fm.moveItem(at:stage,to:destination)
            done = model.bytes; received = 0; update("installed","已下载并通过全部文件校验"); cleanup()
        } catch { fail("安装模型时遇到问题，已保留本地文件。") }
    }
}

if CommandLine.arguments.contains("--boundary-probe") {
    let home = fm.homeDirectoryForCurrentUser
    let paths = [home.appendingPathComponent("Library/Application Support/Guiyu/history.json"),home.appendingPathComponent(".codex/config.toml"),home.appendingPathComponent("Desktop"),URL(fileURLWithPath:"/Volumes")]
    let results = paths.map { url -> [String:Any] in
        let fd = open(url.path,O_RDONLY); let code = errno; if fd>=0 { close(fd) }
        return ["target":url.lastPathComponent,"denied":fd == -1 && (code == EPERM || code == EACCES),"errno":code]
    }
    let report:[String:Any] = ["sandbox":isolated,"private_reads":results,"pid":ProcessInfo.processInfo.processIdentifier]
    let data = try JSONSerialization.data(withJSONObject:report,options:.sortedKeys)
    try ModelStorage.write(report.mapValues { String(describing:$0) },to:root.appendingPathComponent("boundary-probe.json"))
    print(String(decoding:data,as:UTF8.self)); exit(results.allSatisfy { $0["denied"] as? Bool == true } ? 0 : 1)
}
let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
let service = Downloader()
service.tick = Timer.scheduledTimer(withTimeInterval:0.3,repeats:true) { _ in service.poll() }
service.poll()
app.run()
