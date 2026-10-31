import Foundation
import SwiftUI

// Keep the property-wrapper spelling unambiguous with newer SDK State macros.
typealias ViewState<Value> = SwiftUI.State<Value>

enum Page: String, CaseIterable { case workspace = "工作台", library = "我的资料", products = "工作成果", privacy = "隐私空间" }
enum TaskKind: String, CaseIterable {
    case auto, workflow, search, table, statistics, summary, compare, write, organize, answer
    var usesPlan: Bool { [.auto,.workflow,.search,.statistics,.compare,.write,.answer].contains(self) }
    var title: String {
        switch self { case .auto: return "交给归屿安排"; case .workflow: return "多步办公"; case .search: return "资料查找"; case .table: return "提取成表格"; case .statistics: return "统计与核对"; case .summary: return "写一份汇总"; case .compare: return "资料对比"; case .write: return "起草与改写"; case .organize: return "整理文件"; case .answer: return "直接问答" }
    }
    var icon: String {
        switch self { case .auto: return "sparkle"; case .workflow: return "list.bullet.clipboard"; case .search: return "doc.text.magnifyingglass"; case .table: return "tablecells"; case .statistics: return "sum"; case .summary: return "doc.text"; case .compare: return "rectangle.split.2x1"; case .write: return "square.and.pencil"; case .organize: return "folder.badge.gearshape"; case .answer: return "text.bubble" }
    }
    var prompt: String {
        switch self {
        case .workflow: return "查找这些费用资料，提取费用项目、金额和经办人成表格，统计金额的合计与平均值，再写一份报销简报。"
        case .statistics: return "统计这些表格中的数值，核对合计、平均值与范围，保留参与计算的数据。"
        case .write: return "帮我起草一封礼貌的中文邮件，邀请同事周五参加一次30分钟的项目沟通会。未确定的信息留出待补充的位置。"
        case .search: return "查找“交通”相关资料，列出匹配原文和出处。"
        case .table: return "把这些材料中的活动名称、时间、地点和负责人整理成一张表格，附上出处。"
        case .summary: return "根据这些材料写一份清晰的活动汇总，列出安排、待办和还缺的信息，标出出处。"
        case .compare: return "对比这些方案的费用、时间和服务内容，按维度列出原文与出处，再写一份简短的选择说明。"
        case .organize: return "根据内容给这些资料分类，起容易查找的中文文件名，先给我看整理方案。"
        default: return ""
        }
    }
}

struct SourceDoc: Identifiable, Codable, Equatable {
    var id: String
    var name: String
    var path: String
    var preview: String
    var bytes: Int
    init(_ object: [String: Any]) {
        id = object["id"] as? String ?? UUID().uuidString
        name = object["name"] as? String ?? "资料"
        path = object["path"] as? String ?? ""
        preview = object["preview"] as? String ?? ""
        bytes = object["bytes"] as? Int ?? 0
    }
    var icon: String {
        switch URL(fileURLWithPath: name).pathExtension.lowercased() {
        case "xlsx", "csv": return "tablecells"
        case "pdf": return "doc.richtext"
        default: return "doc.text"
        }
    }
}

struct Artifact: Identifiable, Codable {
    var name: String
    var path: String
    var type: String
    var preview: String?
    var columns: [String]?
    var rows: [[String]]?
    var id: String { path }
    init(_ object: [String: Any]) {
        name = object["name"] as? String ?? "结果"
        path = object["path"] as? String ?? ""
        type = object["type"] as? String ?? "docx"
        preview = object["preview"] as? String
        columns = object["columns"] as? [String]
        rows = object["rows"] as? [[String]]
    }
}

struct FileMove: Identifiable, Codable {
    var source: String
    var destination: String
    var name: String
    var newName: String
    var category: String
    var id: String { source }
    init(_ object: [String: Any]) {
        source = object["source"] as? String ?? ""
        destination = object["destination"] as? String ?? ""
        name = object["name"] as? String ?? ""
        newName = object["new_name"] as? String ?? ""
        category = object["category"] as? String ?? ""
    }
}

struct FileTransaction: Identifiable, Codable {
    var id: String
    var state: String
    var moves: [FileMove]
    init(_ object: [String: Any]) {
        id = object["id"] as? String ?? ""
        state = object["state"] as? String ?? "preview"
        moves = (object["moves"] as? [[String: Any]] ?? []).map(FileMove.init)
    }
}

struct LocalToolCall: Identifiable, Codable {
    var id:String
    var tool:String
    var title:String
    var state:String
    var summary:String
    var input:String
    var output:String
    init(_ object:[String:Any]) {
        id = object["id"] as? String ?? UUID().uuidString
        tool = object["tool"] as? String ?? ""
        title = object["title"] as? String ?? ""
        state = object["state"] as? String ?? "failed"
        summary = object["summary"] as? String ?? ""
        input = object["input"] as? String ?? ""
        output = object["output"] as? String ?? ""
    }
}

struct TaskRecord: Identifiable, Codable {
    var id: String
    var kind: String
    var title: String
    var prompt: String
    var text: String
    var artifacts: [Artifact]
    var columns: [String]
    var rows: [[String]]
    var sources: [SourceDoc]
    var threadID: String?
    var parentID: String?
    var querySummary: String?
    var searchHits: [SearchHit]?
    var modelName: String?
    var toolCalls:[LocalToolCall]?
    var transaction: FileTransaction?
    var shareCheck:ShareCheck?
    var plan: AgentPlan?
    var seconds: Double
    var tokensPerSecond: Double
    var memoryGB: Double
    var created: Double
    init(_ object: [String: Any], sourceCache: [SourceDoc] = []) {
        id = object["id"] as? String ?? UUID().uuidString
        kind = object["kind"] as? String ?? "answer"
        title = object["title"] as? String ?? "本地任务"
        prompt = object["prompt"] as? String ?? ""
        text = object["text"] as? String ?? ""
        artifacts = (object["artifacts"] as? [[String: Any]] ?? []).map(Artifact.init)
        columns = object["columns"] as? [String] ?? []
        rows = object["rows"] as? [[String]] ?? []
        sources = (object["sources"] as? [[String: Any]] ?? []).map { item in
            var doc = SourceDoc(item)
            doc.preview = sourceCache.first(where: { $0.path == doc.path })?.preview ?? doc.preview
            return doc
        }
        threadID = object["thread_id"] as? String
        parentID = object["parent_id"] as? String
        querySummary = object["query_summary"] as? String
        searchHits = (object["search_hits"] as? [[String:Any]])?.map(SearchHit.init)
        modelName = object["model_name"] as? String
        toolCalls = (object["tool_calls"] as? [[String:Any]])?.map(LocalToolCall.init)
        transaction = (object["transaction"] as? [String: Any]).map(FileTransaction.init)
        shareCheck=(object["share_check"] as? [String:Any]).map(ShareCheck.init)
        plan = (object["plan"] as? [String: Any]).map(AgentPlan.init)
        let stats = object["stats"] as? [String: Any] ?? [:]
        seconds = stats["seconds"] as? Double ?? 0
        tokensPerSecond = stats["tokens_per_second"] as? Double ?? 0
        memoryGB = stats["peak_memory_gb"] as? Double ?? 0
        created = object["created"] as? Double ?? Date().timeIntervalSince1970
    }
}

extension TaskRecord {
    var displayText:String {
        guard let plan,plan.state=="completed",plan.groundedDelivery != true,plan.completionState=="passed" else { return text }
        let drafts=plan.steps.filter { $0.enabled && $0.state=="completed" && $0.tool=="write" && !$0.output.isEmpty }
        return drafts.isEmpty ? text : drafts.map(\.output).joined(separator:"\n\n")
    }
}

enum Palette {
    static let background = Color(red: 0.972, green: 0.975, blue: 0.958)
    static let sidebar = Color(red: 0.944, green: 0.955, blue: 0.926)
    static let accent = Color(red: 0.19, green: 0.36, blue: 0.30)
    static let ink = Color(red: 0.16, green: 0.22, blue: 0.19)
    static let muted = Color(red: 0.49, green: 0.54, blue: 0.49)
    static let line = Color(red: 0.88, green: 0.90, blue: 0.86)
    static let pale = Color(red: 0.91, green: 0.95, blue: 0.89)
    static let warm = Color(red: 0.72, green: 0.51, blue: 0.30)
}
