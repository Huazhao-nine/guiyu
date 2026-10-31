import Foundation

struct LocalWorkspace: Codable, Identifiable {
    var id: String
    var name: String
    var path: String
}
struct WorkspaceRegistry: Codable { var selectedID: String?; var workspaces: [LocalWorkspace] }
struct WorkspaceFile: Identifiable, Equatable {
    var path: String
    var relativePath: String
    var bytes: Int64
    var id: String { path }
    var name: String { URL(fileURLWithPath:path).lastPathComponent }
    var available: Bool { bytes <= 8*1024*1024 }
}
struct WorkspaceScope: Codable { var paths: [String]; var automatic:Bool? = nil;var indexPaused:Bool? = nil }
enum WorkspaceScanner {
    static let extensions: Set<String> = ["txt","md","pdf","docx","xlsx","csv"]
    static func contains(_ path:String,in root:String)->Bool {
        let candidate = URL(fileURLWithPath:path).resolvingSymlinksInPath().standardizedFileURL.path
        let base = URL(fileURLWithPath:root).resolvingSymlinksInPath().standardizedFileURL.path
        return candidate.hasPrefix(base+"/")
    }
    static func scan(_ path:String) throws -> (files:[WorkspaceFile],limited:Bool) {
        let url = URL(fileURLWithPath:path)
        let fm = FileManager.default
        guard (try url.resourceValues(forKeys:[.isDirectoryKey,.isSymbolicLinkKey])).isDirectory == true,
              url.resolvingSymlinksInPath().standardizedFileURL.path == url.standardizedFileURL.path else { throw CocoaError(.fileReadNoSuchFile) }
        var scanError:Error?
        guard let iterator = fm.enumerator(at:url,includingPropertiesForKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey],options:[.skipsHiddenFiles,.skipsPackageDescendants],errorHandler: { _,error in scanError = error; return true }) else { throw CocoaError(.fileReadNoPermission) }
        var files:[WorkspaceFile] = [], nodes = 0, limited = false
        for case let child as URL in iterator {
            nodes += 1
            if nodes>20000 || files.count>=2000 { limited = true; break }
            let values = try child.resourceValues(forKeys:[.isRegularFileKey,.isSymbolicLinkKey,.fileSizeKey])
            if values.isSymbolicLink == true { continue }
            guard values.isRegularFile == true, extensions.contains(child.pathExtension.lowercased()),contains(child.path,in:path) else { continue }
            let canonical = child.resolvingSymlinksInPath().standardizedFileURL.path
            files.append(WorkspaceFile(path:canonical,relativePath:String(canonical.dropFirst(path.count+1)),bytes:Int64(values.fileSize ?? 0)))
        }
        if let scanError { throw scanError }
        return (files.sorted { $0.relativePath.localizedStandardCompare($1.relativePath) == .orderedAscending },limited)
    }
}
