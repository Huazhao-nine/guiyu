import Foundation

struct SearchHit: Identifiable, Codable {
    var id: String
    var name: String
    var path: String
    var snippet: String
    var line: Int
    init(_ value: [String:Any]) {
        id = value["id"] as? String ?? ""
        name = value["name"] as? String ?? ""
        path = value["path"] as? String ?? ""
        snippet = value["snippet"] as? String ?? ""
        line = value["line"] as? Int ?? 1
    }
}

struct QueryRule: Identifiable, Codable {
    var id = UUID()
    var column = ""
    var operation = "contains"
    var value = ""
    var object: [String:Any] { ["column":column,"operator":operation,"value":value] }
}

struct TableQuery: Codable {
    var rules: [QueryRule] = []
    var match = "all"
    var groupBy = ""
    var metric = ""
    init() {}
    init(_ object: [String:Any]) {
        rules = (object["filters"] as? [[String:Any]] ?? []).map { item in
            var rule = QueryRule(); rule.column = item["column"] as? String ?? ""; rule.operation = item["operator"] as? String ?? "eq"; rule.value = item["value"] as? String ?? ""; return rule
        }
        match = object["match"] as? String ?? "all"
        groupBy = (object["group_by"] as? [String])?.first ?? ""
        metric = (object["metrics"] as? [String])?.first ?? ""
    }
    var object: [String:Any] { ["filters":rules.map(\.object),"match":match,"group_by":groupBy.isEmpty ? [] : [groupBy],"metrics":metric.isEmpty ? [] : [metric]] }
}

struct LocalModelOption: Identifiable, Codable {
    var id: String
    var name: String
    var path: String
    var architecture: String
    var bytes: Int64
    var bits: Int?
    var detail: String { "本机模型文件 · " + ByteCountFormatter.string(fromByteCount:bytes,countStyle:.file) }
    static func inspect(_ url: URL) throws -> LocalModelOption {
        let directory = url.standardizedFileURL
        let configURL = directory.appendingPathComponent("config.json")
        let data = try Data(contentsOf:configURL)
        guard data.count < 16 * 1024 * 1024, let config = try JSONSerialization.jsonObject(with:data) as? [String:Any], let architecture = config["model_type"] as? String,
              architecture.range(of:"^[a-z0-9_]{1,60}$",options:.regularExpression) != nil, config["auto_map"] == nil else {
            throw NSError(domain:"Guiyu",code:1,userInfo:[NSLocalizedDescriptionKey:"当前只支持 MLX LM 内置架构的本地模型。"])
        }
        guard FileManager.default.fileExists(atPath:directory.appendingPathComponent("tokenizer_config.json").path) else {
            throw NSError(domain:"Guiyu",code:2,userInfo:[NSLocalizedDescriptionKey:"模型缺少 tokenizer_config.json。"])
        }
        let weights = try FileManager.default.contentsOfDirectory(at:directory,includingPropertiesForKeys:[.fileSizeKey,.isSymbolicLinkKey]).filter { $0.pathExtension == "safetensors" }
        guard !weights.isEmpty else { throw NSError(domain:"Guiyu",code:3,userInfo:[NSLocalizedDescriptionKey:"请选择包含 safetensors 权重的 MLX 模型文件夹。当前后端不支持 GGUF。"]) }
        var bytes: Int64 = 0
        for file in weights {
            let values = try file.resourceValues(forKeys:[.fileSizeKey,.isSymbolicLinkKey])
            guard values.isSymbolicLink != true else { throw NSError(domain:"Guiyu",code:4,userInfo:[NSLocalizedDescriptionKey:"请添加实际保存在目录内的模型文件。采样快照中的符号链接需先准备为本地文件。"]) }
            bytes += Int64(values.fileSize ?? 0)
        }
        let quantization = (config["quantization"] ?? config["quantization_config"]) as? [String:Any]
        return LocalModelOption(id:UUID().uuidString,name:directory.lastPathComponent,path:directory.path,architecture:architecture,bytes:bytes,bits:quantization?["bits"] as? Int)
    }
}

struct ModelLibrary: Codable {
    var selectedID: String
    var models: [LocalModelOption]
}
