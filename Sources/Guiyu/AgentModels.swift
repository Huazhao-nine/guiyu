import Foundation

struct AgentStep: Identifiable, Codable {
    var id: String
    var tool: String
    var title: String
    var detail: String
    var effect: String
    var instruction: String
    var enabled: Bool
    var state: String
    var summary: String
    var output: String
    var seconds: Double
    var attempts: Int?
    var checkMessage: String?
    var adaptiveAdded: Bool?
    init(_ object: [String: Any]) {
        id = object["id"] as? String ?? UUID().uuidString
        tool = object["tool"] as? String ?? "answer"
        title = object["title"] as? String ?? "本地步骤"
        detail = object["description"] as? String ?? ""
        effect = object["effect"] as? String ?? "read"
        instruction = object["instruction"] as? String ?? ""
        enabled = object["enabled"] as? Bool ?? true
        state = object["state"] as? String ?? "pending"
        summary = object["summary"] as? String ?? ""
        output = object["output"] as? String ?? ""
        seconds = object["seconds"] as? Double ?? 0
        attempts = object["attempts"] as? Int
        checkMessage = (object["check"] as? [String:Any])?["message"] as? String
        adaptiveAdded = object["adaptive_added"] as? Bool
    }
    var icon: String {
        switch tool { case "workbook": return "tablecells"; case "share": return "eye.slash"; case "calculate": return "function"; case "calendar": return "calendar"; case "search": return "doc.text.magnifyingglass"; case "table": return "tablecells"; case "filter": return "line.3.horizontal.decrease.circle"; case "statistics": return "sum"; case "summary": return "text.alignleft"; case "compare": return "rectangle.split.2x1"; case "write": return "square.and.pencil"; case "organize": return "folder.badge.gearshape"; default: return "text.bubble" }
    }
}

struct AgentActivity: Identifiable, Codable {
    var kind: String
    var message: String
    var created: Double
    var id: String { "\(created)-\(kind)-\(message)" }
    init(_ object:[String:Any]) {
        kind = object["kind"] as? String ?? "checked"
        message = object["message"] as? String ?? ""
        created = object["created"] as? Double ?? 0
    }
}

struct AgentPlan: Identifiable, Codable {
    var id: String
    var prompt: String
    var title: String
    var state: String
    var paths: [String]
    var sourceNames: [String]
    var steps: [AgentStep]
    var error: String?
    var threadID: String?
    var querySummary: String?
    var reusedTable: Bool?
    var retrieval:RetrievalEvidence?
    var planningNote: String?
    var preferenceSummary: String?
    var adaptive: Bool?
    var events: [AgentActivity]?
    var plannerSource: String?
    var groundedDelivery: Bool?
    var completionMessage: String?
    var completionState: String?
    init(_ object: [String: Any]) {
        id = object["id"] as? String ?? ""
        prompt = object["prompt"] as? String ?? ""
        title = object["title"] as? String ?? "本地办公任务"
        state = object["state"] as? String ?? "draft"
        paths = object["paths"] as? [String] ?? []
        sourceNames = object["source_names"] as? [String] ?? []
        steps = (object["steps"] as? [[String: Any]] ?? []).map(AgentStep.init)
        error = object["error"] as? String
        threadID = object["thread_id"] as? String
        querySummary = object["query_summary"] as? String
        reusedTable = object["reused_table"] as? Bool
        retrieval = (object["retrieval"] as? [String:Any]).map(RetrievalEvidence.init)
        planningNote = object["planning_note"] as? String
        preferenceSummary = object["preference_summary"] as? String
        adaptive = object["adaptive"] as? Bool
        events = (object["events"] as? [[String:Any]])?.map(AgentActivity.init)
        plannerSource = object["planner_source"] as? String
        groundedDelivery = object["grounded_delivery"] as? Bool
        completionMessage = (object["completion_check"] as? [String:Any])?["message"] as? String
        completionState = (object["completion_check"] as? [String:Any])?["state"] as? String
    }
    var canContinue: Bool { ["draft","paused","failed"].contains(state) }
    var completedCount: Int { steps.filter { $0.state == "completed" }.count }
    var enabledCount: Int { steps.filter(\.enabled).count }
    var pendingCount: Int { steps.filter { $0.enabled && $0.state != "completed" }.count }
}

// Explicit edits to an existing workbook result retain their source context.
struct WorkbookFollowupIntent {
    static func requiresSource(_ prompt:String,parent:TaskRecord?) -> Bool {
        guard let plan=parent?.plan,plan.state=="completed",!plan.paths.isEmpty,
              plan.steps.contains(where:{$0.tool=="workbook"}) else { return false }
        func has(_ pattern:String)->Bool { prompt.range(of:pattern,options:[.regularExpression,.caseInsensitive]) != nil }
        if has("另外|另一个|另一份|换.{0,4}(文件|工作簿|资料|数据源)|不沿用|不要沿用") { return false }
        let context="(其他|其它|其余|原有|原来).{0,30}(不变|照旧|保持)|(上轮|上次|刚才|这批|这些|当前).{0,8}(结果|筛选|明细|条件|表格|工作簿|资料)|原始(数据|明细|记录).{0,4}(重算|重做)|沿用.{0,4}(上轮|原有|之前)"
        let action="改|调整|放宽|收紧|保留|筛|排序|分组|汇总|统计|导出|加上|去掉|去重|只留|只要|选择|重算|重做"
        return has(context) && has(action)
    }
}

// Session-only intent: a restored plan never carries permission to restart.
struct AutomaticPlanGate {
    private var requestID:String?
    mutating func arm(id:String,prompt:String) {
        let pattern="先(给我|给|看看|看下|列出|拟定|拟个|出个).{0,2}(计划|方案|步骤)|(只|仅)(给我|给|看|要|需|需要|列出|生成|提供|出)(一份|一个|执行)?(计划|方案|步骤)|(不要|先别|暂不|不必|不需要|先不|先不要|暂时不).{0,3}(执行|开始|处理)|plan only|do not execute"
        requestID=prompt.range(of:pattern,options:[.regularExpression,.caseInsensitive]) == nil ? id : nil
    }
    mutating func clear() { requestID=nil }
    mutating func consume(_ plan:AgentPlan,requestID responseID:String? = nil)->Bool {
        guard let responseID,requestID==responseID,plan.state=="draft" else { return false }
        requestID=nil
        let effects=["workbook":"create","share":"create","search":"read","table":"create","filter":"create","statistics":"create","summary":"create","compare":"create","calculate":"read","calendar":"read","write":"create","answer":"read","organize":"preview"]
        return !plan.steps.isEmpty && plan.steps.filter(\.enabled).allSatisfy{effects[$0.tool]==$0.effect}
    }
}
