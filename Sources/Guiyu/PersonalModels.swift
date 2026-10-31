import Foundation

struct PersonalPreferences: Codable, Equatable {
    var enabled = false
    var tone = "清晰自然"
    var length = "适中"
    var notes = ""
    static let tones = ["清晰自然","正式简洁","亲切自然"]
    static let lengths = ["适中","简短","详细"]
    var object: [String:Any] { ["enabled":enabled,"tone":tone,"length":length,"notes":String(notes.prefix(600))] }
    var summary: String { enabled ? "\(tone) · \(length)" : "每次按当前要求表达" }
}

struct WorkProduct: Identifiable {
    let record: TaskRecord
    let artifact: Artifact
    var id: String { record.id+"|"+artifact.path }
    var title: String { record.prompt }
    var isComplete: Bool { record.plan == nil || record.plan?.state == "completed" }
}

enum ProductFiles {
    static func validatedURL(_ artifact: Artifact, dataDir: URL) -> URL? {
        let url = URL(fileURLWithPath:artifact.path).standardizedFileURL
        let base = dataDir.appendingPathComponent("Outputs").standardizedFileURL
        guard ["xlsx","docx","md"].contains(artifact.type),url.pathExtension.lowercased() == artifact.type,
              base.resolvingSymlinksInPath().path == base.path,
              url.path.hasPrefix(base.path+"/"),url.resolvingSymlinksInPath().path == url.path,
              let values = try? url.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey]),
              values.isRegularFile == true,values.isSymbolicLink != true else { return nil }
        return url
    }
}
