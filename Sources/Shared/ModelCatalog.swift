import Foundation
import Darwin

struct CatalogFile: Codable {
    var name: String
    var bytes: Int64
    var sha256: String
    var remotePath: String?
    var url: String?
    func downloadURL(repository:String,revision:String)->URL? {
        if let url {
            guard let parsed=URL(string:url),parsed.scheme == "https",parsed.host == "files.pythonhosted.org",parsed.user == nil,parsed.password == nil,parsed.query == nil,parsed.path.hasSuffix(".whl") else { return nil }
            return parsed
        }
        let path=remotePath ?? name
        guard path.split(separator:"/").allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." && $0.range(of:"^[A-Za-z0-9_.-]+$",options:.regularExpression) != nil }),!path.hasPrefix("/"),!path.contains("//"),revision.range(of:"^[a-f0-9]{40}$",options:.regularExpression) != nil else { return nil }
        return URL(string:"https://huggingface.co/\(repository)/resolve/\(revision)/\(path)?download=true")
    }
}
struct CatalogModel: Codable, Identifiable {
    var id: String
    var name: String
    var badge: String
    var summary: String
    var memory: String
    var repository: String
    var revision: String
    var license: String
    var files: [CatalogFile]
    var purpose:String?
    var advanced:Bool?
    var recommended:Bool?
    var isEmbedding:Bool { purpose == "embedding" }
    var isPrivacy:Bool { purpose == "privacy" }
    var bytes: Int64 { files.reduce(0) { $0 + $1.bytes } }
    static func load() -> [CatalogModel] {
        guard let url = Bundle.main.url(forResource:"model-catalog",withExtension:"json"),
              let data = try? Data(contentsOf:url), let models = try? JSONDecoder().decode([CatalogModel].self,from:data) else { return [] }
        return models
    }
}
struct ModelDownloadStatus: Codable {
    var modelID: String
    var phase: String
    var completed: Int64
    var total: Int64
    var detail: String
    var updated: Double = Date().timeIntervalSince1970
    var progress: Double { total > 0 ? min(1,Double(completed)/Double(total)) : 0 }
    var active: Bool { ["starting","downloading","verifying","pausing"].contains(phase) }
}
enum ModelStorage {
    static var root: URL { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/GuiyuModels",isDirectory:true) }
    static func installed(_ id: String) -> URL { root.appendingPathComponent("Installed/"+id,isDirectory:true) }
    static func status(_ id: String) -> URL { root.appendingPathComponent(id+".status.json") }
    static func write<T:Encodable>(_ value:T,to url:URL) throws {
        let data = try JSONEncoder().encode(value)
        let temporary = url.deletingLastPathComponent().appendingPathComponent("."+UUID().uuidString+".tmp")
        let fd = open(temporary.path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0o600)
        guard fd>=0 else { throw POSIXError(.EACCES) }
        let handle = FileHandle(fileDescriptor:fd,closeOnDealloc:true)
        do {
            try handle.write(contentsOf:data); try handle.synchronize(); try handle.close()
            guard rename(temporary.path,url.path) == 0 else { throw POSIXError(.EIO) }
        } catch { try? handle.close(); try? FileManager.default.removeItem(at:temporary); throw error }
    }
}
