import AppKit
import Foundation

@main struct WorkspaceChecks {
    @MainActor static func main() throws {
        let fm = FileManager.default
        var largeModel=LocalModelOption(id:"large",name:"Large",path:"/nonexistent",architecture:"gpt_oss",bytes:12_000_000_000,bits:4)
        precondition(!DevicePolicy.allows(largeModel,memoryBytes:16*1024*1024*1024))
        precondition(!DevicePolicy.allows(largeModel,memoryBytes:24*1024*1024*1024))
        precondition(DevicePolicy.allows(largeModel,memoryBytes:32*1024*1024*1024))
        var dailyModel=largeModel;dailyModel.bytes=6_000_000_000
        precondition(DevicePolicy.allows(dailyModel,memoryBytes:16*1024*1024*1024))
        let base = fm.temporaryDirectory.appendingPathComponent("guiyu-native-"+UUID().uuidString)
        try fm.createDirectory(at:base,withIntermediateDirectories:true)
        defer { try? fm.removeItem(at:base) }
        // Tool traces survive saved-history round trips; pre-tool records still decode.
        let toolObject:[String:Any] = ["id":"calc-1","tool":"calculator","title":"核对平摊费用","state":"completed","summary":"每人 164.50 元","input":"(368 + 125.5) ÷ 3，保留两位小数","output":"164.50 元/人"]
        let toolCall = LocalToolCall(toolObject)
        let savedCall = try JSONDecoder().decode(LocalToolCall.self,from:JSONEncoder().encode(toolCall))
        precondition(savedCall.id == toolCall.id && savedCall.tool == toolCall.tool && savedCall.title == toolCall.title)
        precondition(savedCall.state == toolCall.state && savedCall.summary == toolCall.summary && savedCall.input == toolCall.input && savedCall.output == toolCall.output)
        let toolRecord = TaskRecord(["id":"工具任务","kind":"chat","prompt":"平摊费用","text":"每人 164.50 元。","tool_calls":[toolObject]])
        precondition(toolRecord.toolCalls?.count == 1 && toolRecord.toolCalls?.first?.id == "calc-1")
        let savedHistory = base.appendingPathComponent("tool-history.json")
        try JSONEncoder().encode([toolRecord,TaskRecord(["id":"旧任务","text":"原有记录"]) ]).write(to:savedHistory)
        let restoredHistory = try JSONDecoder().decode([TaskRecord].self,from:Data(contentsOf:savedHistory))
        precondition(restoredHistory.count == 2 && restoredHistory[0].toolCalls?.first?.output == "164.50 元/人")
        precondition(restoredHistory[1].toolCalls == nil && restoredHistory[1].text == "原有记录")
        var legacyObject = try JSONSerialization.jsonObject(with:JSONEncoder().encode(toolRecord)) as! [String:Any]
        legacyObject.removeValue(forKey:"toolCalls")
        let legacyRecord = try JSONDecoder().decode(TaskRecord.self,from:JSONSerialization.data(withJSONObject:legacyObject))
        precondition(legacyRecord.toolCalls == nil && legacyRecord.id == toolRecord.id)
        legacyObject["toolCalls"] = NSNull()
        let nullTraceRecord = try JSONDecoder().decode(TaskRecord.self,from:JSONSerialization.data(withJSONObject:legacyObject))
        precondition(nullTraceRecord.toolCalls == nil)
        let a = base.appendingPathComponent("A"), b = base.appendingPathComponent("B")
        try fm.createDirectory(at:a.appendingPathComponent("sub"),withIntermediateDirectories:true)
        try fm.createDirectory(at:b,withIntermediateDirectories:true)
        try Data("甲的资料".utf8).write(to:a.appendingPathComponent("sub/一.txt"))
        try Data("隐藏".utf8).write(to:a.appendingPathComponent(".隐藏.txt"))
        try Data("乙的资料".utf8).write(to:b.appendingPathComponent("二.txt"))
        try fm.createSymbolicLink(at:a.appendingPathComponent("外部.txt"),withDestinationURL:b.appendingPathComponent("二.txt"))
        try fm.createSymbolicLink(at:a.appendingPathComponent("链接目录"),withDestinationURL:b)
        let inventory = try WorkspaceScanner.scan(a.path)
        precondition(inventory.files.count == 1 && inventory.files[0].relativePath == "sub/一.txt")
        precondition(!WorkspaceScanner.contains(b.appendingPathComponent("二.txt").path,in:a.path))
        precondition(!WorkspaceScanner.contains(a.appendingPathComponent("外部.txt").path,in:a.path))
        precondition(!WorkspaceScanner.contains(a.path+"-another/一.txt",in:a.path))
        let huge = a.appendingPathComponent("大文件.csv")
        fm.createFile(atPath:huge.path,contents:nil)
        let handle = try FileHandle(forWritingTo:huge); try handle.truncate(atOffset:9*1024*1024); try handle.close()
        let withHuge = try WorkspaceScanner.scan(a.path)
        precondition(withHuge.files.first(where:{$0.path == huge.path})?.available == false)
        setenv("GUIYU_DATA_DIR",base.appendingPathComponent("Data").path,1)
        let dataRoot=base.appendingPathComponent("Data")
        try fm.createDirectory(at:dataRoot,withIntermediateDirectories:true)
        var candidate=dailyModel;candidate.id="qwen3.5-9b";candidate.name="Qwen3.5 9B"
        try ModelStorage.write(ModelLibrary(selectedID:largeModel.id,models:[candidate,largeModel]),to:dataRoot.appendingPathComponent("local-models.json"))
        let shareRecord=TaskRecord(["id":"share","text":"可分享正文","share_check":["state":"passed","detector":"AstrLink Guard","source_count":1,"redactions":5,"counts":["姓名":1],"message":"已复查","scope":"文字副本"]])
        let restoredShare=try JSONDecoder().decode(TaskRecord.self,from:JSONEncoder().encode(shareRecord))
        precondition(restoredShare.shareCheck?.sourceCount==1 && restoredShare.shareCheck?.counts["姓名"]==1)
        precondition(TaskRecord(["id":"legacy"]).shareCheck==nil)
        var gate=AutomaticPlanGate()
        let workbookParent=TaskRecord(["id":"data-parent","plan":["id":"data-plan","state":"completed","paths":["/fixture/data.xlsx"],"steps":[["tool":"workbook","effect":"create"]]]])
        for goal in ["把门槛改成不少于300元，其他条件、排序和输出字段不变。","保留上轮筛选条件，从原始明细重算，按部门汇总。","把这些结果按日期排序。","回到刚才的工作簿，从原始记录重算，把金额门槛改成不少于40元，其他要求不变。"] {
            precondition(WorkbookFollowupIntent.requiresSource(goal,parent:workbookParent))
        }
        for goal in ["你是谁？","谢谢，解释一下条件筛选是什么。","现在帮我写一句感谢。","换另一个工作簿，按上轮条件筛选。"] {
            precondition(!WorkbookFollowupIntent.requiresSource(goal,parent:workbookParent))
        }
        precondition(!WorkbookFollowupIntent.requiresSource("上轮结果按日期排序",parent:nil))
        precondition(!WorkbookFollowupIntent.requiresSource("上轮结果按日期排序",parent:TaskRecord(["id":"chat","kind":"chat"])))
        let safe=AgentPlan(["id":"separate-plan-id","state":"draft","steps":[["tool":"write","effect":"create"]]])
        gate.arm(id:"new",prompt:"只用活动方案.md，计算全部筹备费用和剩余预算，核对活动日期提前7天是哪一天，再写一份简短筹备说明，导出Word。保留费用尚未付款这一条件。")
        precondition(gate.consume(safe,requestID:"new"));precondition(!gate.consume(safe,requestID:"new"))
        gate.arm(id:"new",prompt:"先给我计划，不要执行")
        precondition(!gate.consume(safe,requestID:"new"))
        for instruction in ["只给我计划","只看方案","不要执行，只列出步骤","先给我计划，不要执行"] { gate.arm(id:"new",prompt:instruction);precondition(!gate.consume(safe,requestID:"new")) }
        gate.arm(id:"different",prompt:"帮我写通知")
        precondition(!gate.consume(safe,requestID:"new"))
        gate.arm(id:"new",prompt:"帮我写通知");gate.clear();precondition(!gate.consume(safe,requestID:"new"))
        gate.arm(id:"new",prompt:"整理资料")
        precondition(!gate.consume(AgentPlan(["id":"new","state":"draft","steps":[["tool":"organize","effect":"apply"]]]),requestID:"new"))
        gate.arm(id:"new",prompt:"整理资料")
        precondition(gate.consume(AgentPlan(["id":"new","state":"draft","steps":[["tool":"organize","effect":"preview"]]]),requestID:"new"))
        gate.arm(id:"workbook-task",prompt:"按区域分组统计，导出工作簿")
        precondition(gate.consume(AgentPlan(["id":"data-plan","state":"draft","steps":[["tool":"workbook","effect":"create"]]]),requestID:"workbook-task"))
        gate.arm(id:"workbook-write",prompt:"处理工作簿并写简报")
        precondition(gate.consume(AgentPlan(["id":"data-write-plan","state":"draft","steps":[["tool":"workbook","effect":"create"],["tool":"write","effect":"create"]]]),requestID:"workbook-write"))
        gate.arm(id:"unsafe-data",prompt:"处理工作簿")
        precondition(!gate.consume(AgentPlan(["id":"unsafe-plan","state":"draft","steps":[["tool":"workbook","effect":"apply"]]]),requestID:"unsafe-data"))
        var restoredGate=AutomaticPlanGate();precondition(!restoredGate.consume(safe))
        let imported=base.appendingPathComponent("manual-model")
        try fm.createDirectory(at:imported,withIntermediateDirectories:true)
        try Data("{}".utf8).write(to:imported.appendingPathComponent("config.json"))
        largeModel.path=imported.path
        try ModelStorage.write(ModelLibrary(selectedID:largeModel.id,models:[candidate,largeModel]),to:dataRoot.appendingPathComponent("local-models.json"))
        let placeholder=PrimaryModel.placeholder(storage:base)
        precondition(!DevicePolicy.allows(placeholder,memoryBytes:24*1024*1024*1024))
        var downloaded=placeholder;downloaded.bytes=20_402_204_271
        let replaced=PrimaryModel.merging(downloaded,into:[placeholder,downloaded])
        precondition(replaced.count==1 && replaced[0].bytes>0)
        let store = Store(root:base,hostSandboxed:false)
        precondition(store.selectedModelID==PrimaryModel.id)
        precondition(!store.localModels.contains(where:{$0.id=="default-qwen3"}))
        precondition(store.localModels.contains(where:{$0.id==largeModel.id}))
        store.selectedModelID=largeModel.id;store.persistModels()
        let restarted=Store(root:base,hostSandboxed:false)
        precondition(restarted.selectedModelID==largeModel.id)
        precondition(restarted.localModels.contains(where:{$0.id==largeModel.id}))
        let wa = LocalWorkspace(id:UUID().uuidString,name:"甲",path:a.path), wb = LocalWorkspace(id:UUID().uuidString,name:"乙",path:b.path)
        store.workspaces = [wa,wb]
        store.activeWorkspaceID = wa.id; store.loadWorkspaceState()
        store.selectedPaths = [inventory.files[0].path]; store.persistScope()
        let record = TaskRecord(["id":"甲的任务","prompt":"只统计甲","text":"100"])
        store.history = [record]; store.persistHistory()
        store.current = record; store.activeThreadID = "甲的任务"; store.schemaColumns = ["甲字段"]
        store.switchWorkspace(wb.id)
        precondition(store.current == nil && store.history.isEmpty && store.schemaColumns.isEmpty && store.activeThreadID == nil)
        precondition(store.dataDir.lastPathComponent == wb.id)
        // Scanning is asynchronous. Test deterministic persistence independently here.
        store.workspaceScanning = false
        store.selectedPaths = [b.appendingPathComponent("二.txt").path]; store.persistScope()
        store.history = [TaskRecord(["id":"乙的任务","prompt":"只统计乙","text":"200"])]; store.persistHistory()
        store.switchWorkspace(wa.id)
        precondition(store.history.count == 1 && store.history[0].id == "甲的任务")
        precondition(store.selectedPaths == [inventory.files[0].path])
        store.workspaceScanning = false
        store.workspaceFiles = inventory.files
        store.setWorkspaceSelection([b.appendingPathComponent("二.txt").path])
        precondition(store.selectedPaths.isEmpty)
        store.renameWorkspace(wa.id,"新的名字")
        let registry = try JSONDecoder().decode(WorkspaceRegistry.self,from:Data(contentsOf:store.baseDataDir.appendingPathComponent("workspaces.json")))
        precondition(registry.workspaces.first?.name == "新的名字")
        // Larger folders are browsable; task selection remains bounded independently.
        let large = base.appendingPathComponent("Large")
        try fm.createDirectory(at:large,withIntermediateDirectories:true)
        for i in 0..<45 { try Data("文档".utf8).write(to:large.appendingPathComponent("\(i).txt")) }
        let many = try WorkspaceScanner.scan(large.path)
        precondition(many.files.count == 45)
        // Result actions must stay inside the current workspace's real Outputs tree.
        let outputs = store.dataDir.appendingPathComponent("Outputs/example")
        try fm.createDirectory(at:outputs,withIntermediateDirectories:true)
        let resultFile = outputs.appendingPathComponent("文稿.md")
        try Data("原稿".utf8).write(to:resultFile)
        let artifact = Artifact(["name":"文稿.md","path":resultFile.path,"type":"md"])
        precondition(ProductFiles.validatedURL(artifact,dataDir:store.dataDir) != nil)
        let externalArtifact = Artifact(["path":b.appendingPathComponent("二.txt").path,"type":"md"])
        precondition(ProductFiles.validatedURL(externalArtifact,dataDir:store.dataDir) == nil)
        let alias = outputs.appendingPathComponent("链接.md")
        try fm.createSymbolicLink(at:alias,withDestinationURL:resultFile)
        precondition(ProductFiles.validatedURL(Artifact(["path":alias.path,"type":"md"]),dataDir:store.dataDir) == nil)
        var prefs = PersonalPreferences();prefs.enabled = true;prefs.tone = "正式简洁";prefs.notes = "先说结论"
        store.workspaceScanning = false
        precondition(store.savePreferences(prefs))
        let persistedPrefs = try JSONDecoder().decode(PersonalPreferences.self,from:Data(contentsOf:store.baseDataDir.appendingPathComponent("preferences.json")))
        precondition(persistedPrefs == prefs)
        store.history = [TaskRecord(["id":"成果隔离","prompt":"甲的文稿","artifacts":[["name":"文稿.md","path":resultFile.path,"type":"md"]]])]
        store.persistHistory();precondition(store.workProducts.count == 1)
        store.switchWorkspace(wb.id)
        precondition(store.workProducts.isEmpty)
        store.workspaceScanning = false;store.switchWorkspace(wa.id)
        precondition(store.workProducts.count == 1)
        store.workspaceScanning = false
        // General conversation bypasses the index even when it is paused.
        let selectedBeforeChat = store.selectedPaths
        store.indexUserPaused = true; store.workspaceAutomatic = true
        store.pendingRouting = ["id":"chat-turn","prompt":"你是谁","paths":selectedBeforeChat]
        store.isBusy = true; store.isPlanning = true; store.errorMessage = nil
        store.completeTaskRouting(["mode":"chat","use_previous":false])
        precondition(store.responseMode == "chat" && !store.isPlanning && store.pendingRetrieval == nil && store.errorMessage == nil)
        precondition(store.selectedPaths == selectedBeforeChat && store.pendingRouting == nil)
        // Source-free tools must also bypass a paused workspace index, retaining
        // the user's selected source scope for later workspace questions.
        store.documents = [SourceDoc(["id":"甲资料","name":"一.txt","path":inventory.files[0].path,"preview":"甲的资料"])]
        let documentsBeforeTools = store.documents
        store.pendingRouting = ["id":"tools-turn","prompt":"午餐368元、交通125.5元，3个人平摊","paths":selectedBeforeChat,"parent_id":"旧资料任务","query":["filters":["甲"]]]
        store.isPlanning = true
        store.completeTaskRouting(["mode":"tools","use_previous":false])
        precondition(store.responseMode == "tools" && !store.isPlanning && store.isBusy)
        precondition(store.indexUserPaused && store.pendingRetrieval == nil && store.pendingRouting == nil && store.errorMessage == nil)
        precondition(store.selectedPaths == selectedBeforeChat && store.documents == documentsBeforeTools)
        store.pendingRouting = ["id":"write-turn","prompt":"写邀请函","paths":selectedBeforeChat]
        store.completeTaskRouting(["mode":"task","use_previous":false])
        precondition(store.responseMode == "task" && store.pendingRetrieval == nil && store.errorMessage == nil)
        store.pendingRouting = ["id":"source-turn","prompt":"查费用","paths":selectedBeforeChat]
        store.completeTaskRouting(["mode":"workspace","use_previous":false])
        precondition(store.errorMessage?.contains("暂停") == true && !store.isBusy && store.pendingRetrieval == nil)
        store.errorMessage = nil; store.isBusy = true; store.responseMode = "workspace"
        store.pendingRetrieval = ["id":"missing-sources","prompt":"查找不存在的记录"]
        store.completeWorkspaceRetrieval(result:["paths":[String]()])
        precondition(!store.isBusy && store.errorMessage?.contains("没有找到") == true && store.responseMode != "chat" && store.pendingRetrieval == nil)
        store.errorMessage = nil; store.indexUserPaused = false; store.isPlanning = false
        // Live events belong only to the current in-flight turn. New tasks and
        // opened records must not inherit another turn's transient tool trace.
        store.liveToolCalls = [toolCall]
        store.newTask()
        precondition(store.liveToolCalls.isEmpty && store.current == nil && store.responseMode.isEmpty)
        // With a ready worker, source-free history must not enter inspect().
        // This isolated Store has no worker pipe, so isInspecting is the direct
        // observable effect of dispatching document inspection, without a model.
        store.ready = true
        store.prompt = "保留未发送的草稿"
        store.errorMessage = "所选位置没有可读取的资料"; store.notice = "上一轮提示"
        store.liveToolCalls = [toolCall]
        store.openRecord(legacyRecord)
        precondition(store.liveToolCalls.isEmpty && store.current?.id == legacyRecord.id && store.current?.toolCalls == nil)
        // A failed source task can restore an earlier source-free response.
        // Its absent trace must not fall through to the failed turn's calls.
        store.liveToolCalls = [toolCall]
        precondition(store.displayedToolCalls.isEmpty)
        precondition(!store.isInspecting && store.selectedPaths.isEmpty && store.documents.isEmpty)
        precondition(store.errorMessage == nil && store.notice == nil && store.prompt == "保留未发送的草稿")
        store.errorMessage = "上一轮错误"; store.notice = "上一轮提示"
        store.liveToolCalls = [LocalToolCall(["id":"other-turn","tool":"calendar","state":"running"])]
        store.openRecord(toolRecord)
        precondition(store.liveToolCalls.isEmpty && store.current?.id == toolRecord.id && store.current?.toolCalls?.first?.id == "calc-1")
        store.liveToolCalls = [LocalToolCall(["id":"failed-source-call","tool":"workbook","state":"failed"])]
        precondition(store.displayedToolCalls.map(\.id) == ["calc-1"])
        precondition(!store.isInspecting && store.selectedPaths.isEmpty && store.errorMessage == nil && store.notice == nil)
        precondition(store.prompt == "保留未发送的草稿")
        let sourcedRecord = TaskRecord(["id":"含资料的任务","prompt":"查甲的资料","sources":[["id":"甲资料","name":"一.txt","path":inventory.files[0].path,"preview":"甲的资料"]]])
        store.openRecord(sourcedRecord)
        precondition(store.current?.id == sourcedRecord.id && store.selectedPaths == [inventory.files[0].path])
        precondition(store.documents == sourcedRecord.sources && store.isInspecting)
        store.isInspecting = false; store.ready = false
        precondition(ModelDownloadStatus(modelID:"test",phase:"pausing",completed:0,total:1,detail:"").active)
        store.chooseFiles()
        precondition(store.page == .library)
        store.workspaceScanning = true
        let before = store.selectedPaths
        store.useDemo()
        precondition(store.selectedPaths == before && store.activeWorkspaceID == wa.id)
        var presentation=TaskRecord(["id":"presentation","kind":"workflow","text":"原文与全部步骤","plan":["id":"p","state":"completed","completion_check":["state":"passed"],"steps":[["id":"step-1","tool":"answer","state":"completed","enabled":true,"output":"原文"],["id":"step-2","tool":"write","state":"completed","enabled":true,"output":"核对后的成稿"]]]])
        precondition(presentation.displayText=="核对后的成稿" && presentation.text=="原文与全部步骤")
        presentation.plan?.groundedDelivery=true
        precondition(presentation.displayText==presentation.text)
        presentation.plan?.groundedDelivery=false;presentation.plan?.completionState="partial"
        precondition(presentation.displayText==presentation.text)
        print("NATIVE_WORKSPACE_CHECKS_PASS: 32GB advanced admission with16GB daily compatibility, model selection, workspace/product boundaries, tool trace compatibility/lifecycle, source-free inspection guards, final checked draft presentation with original/intermediate evidence retained")
    }
}
