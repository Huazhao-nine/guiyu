import AppKit
import Foundation
import SwiftUI

struct OfficeExample: Decodable, Identifiable {
    let id:String
    let title:String
    let prompt:String
    let category:String
    static var all:[OfficeExample] {
        struct Suite:Decodable { let cases:[OfficeExample] }
        guard let url=Bundle.main.url(forResource:"office-showcase-tasks",withExtension:"json"),
              let data=try? Data(contentsOf:url),let suite=try? JSONDecoder().decode(Suite.self,from:data) else { return [] }
        return suite.cases.filter { $0.id != "followup" }
    }
    var icon:String {
        switch category { case "statistics":return "chart.bar.xaxis";case "answer":return "doc.text.magnifyingglass";case "organize":return "folder.badge.gearshape";case "missing":return "questionmark.folder";default:return "square.and.pencil" }
    }
}

extension Store {
    private var officeDemoMarker:URL { baseDataDir.appendingPathComponent("office-showcase-v0.9") }
    var isOfficeDemo:Bool {
        guard let activeWorkspaceID,let saved=try? String(contentsOf:officeDemoMarker,encoding:.utf8) else { return false }
        return saved==activeWorkspaceID
    }
    func openOfficeShowcase() {
        guard !contextLocked else { return }
        if let id=try? String(contentsOf:officeDemoMarker,encoding:.utf8),let existing=workspaces.first(where:{$0.id==id}),FileManager.default.fileExists(atPath:existing.path) {
            if activeWorkspaceID != id { switchWorkspace(id) } else { newTask();page = .workspace }
            showWorkspacePicker=false;return
        }
        guard let resources=Bundle.main.resourceURL else { return }
        let id=UUID().uuidString
        // Sibling folder is outside the private history/index exclusion. Every
        // copy has a unique path; reopening never overwrites edited examples.
        let parent=baseDataDir.deletingLastPathComponent().appendingPathComponent("GuiyuExamples/"+id,isDirectory:true)
        let destination=parent.appendingPathComponent("日常办公示例",isDirectory:true)
        do {
            try FileManager.default.createDirectory(at:parent,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            try FileManager.default.copyItem(at:resources.appendingPathComponent("office-showcase"),to:destination)
            try id.write(to:officeDemoMarker,atomically:true,encoding:.utf8)
            try FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:officeDemoMarker.path)
            workspaces.append(LocalWorkspace(id:id,name:"日常办公示例",path:destination.path))
            switchWorkspace(id);notice="18 份虚构资料已就位，选一个任务开始体验"
        } catch { errorMessage="样例工作区暂时无法建立，请检查本机磁盘空间与权限。" }
    }
    func useOfficeExample(_ example:OfficeExample) {
        guard !contextLocked,isOfficeDemo else { return }
        newTask();workspaceAutomatic=true;selectedPaths=[];documents=[];persistScope()
        intelligentExecution=true;kind = .auto;prompt=example.prompt;page = .workspace
        notice="已填好要求，可以修改后再开始"
    }
}

struct OfficeShowcaseView:View {
    @EnvironmentObject var store:Store
    @ViewState private var expanded=false
    private let featured:Set<String>=["meeting_email","conditional_stats","project_brief","procurement","payment_conditions","hard_conditions"]
    var body:some View {
        VStack(alignment:.leading,spacing:20) {
            HStack { Label("日常办公示例",systemImage:"sparkles").font(.system(size:11,weight:.medium)).foregroundStyle(Palette.accent);Spacer();Text("18 份虚构资料 · 可以放心体验").font(.system(size:10)).foregroundStyle(Palette.muted) }
            Text("从一件具体的事开始。") .font(.custom("Songti SC",size:32)).foregroundStyle(Palette.ink)
            Text("可以直接交流，也可以让归屿处理工作。需要资料时，它会自己查找工作区、核对条件，再完成结果。") .font(.system(size:12)).foregroundStyle(Palette.muted).lineSpacing(6)
            HStack(spacing:10) {
                conversationStarter("认识归屿",prompt:"你是谁？你能帮我做什么？")
                conversationStarter("解释一个概念",prompt:"用一个生活例子解释什么是开源软件。")
                conversationStarter("写一句感谢",prompt:"帮我写一句感谢同事配合的消息，语气自然一点。")
            }
            HStack(spacing:10) {
                conversationStarter("算一笔平摊费用",prompt:"帮我算：午餐368元、交通125.5元，3个人平摊，每人多少元？保留两位小数。",icon:"function")
                conversationStarter("确认下周五日期",prompt:"下周五是几月几日？请告诉我日期和星期。",icon:"calendar")
            }.padding(.top,-10)
            Button { store.useComposedDemo() } label: { Label("体验资料、预算与日期协作 →",systemImage:"point.3.connected.trianglepath.dotted").font(.system(size:11)).foregroundStyle(Palette.accent) }.buttonStyle(.plain).disabled(store.contextLocked)
            Button { store.useShareDemo() } label: { Label("体验可分享副本 →",systemImage:"checkmark.shield").font(.system(size:11)).foregroundStyle(Palette.accent) }.buttonStyle(.plain).disabled(store.contextLocked)
            Button { store.useNovelOfficeDemo() } label: { Label("体验更多办公资料 →",systemImage:"tablecells").font(.system(size:11)).foregroundStyle(Palette.accent) }.buttonStyle(.plain).disabled(store.contextLocked)
            LazyVGrid(columns:[GridItem(.flexible()),GridItem(.flexible())],spacing:12) {
                ForEach(OfficeExample.all.filter { featured.contains($0.id) }) { task in taskCard(task) }
            }
            DisclosureGroup(isExpanded:$expanded) {
                LazyVGrid(columns:[GridItem(.flexible()),GridItem(.flexible())],spacing:10) {
                    ForEach(OfficeExample.all.filter { !featured.contains($0.id) }) { task in taskCard(task) }
                }.padding(.top,12)
            } label: { Text("查制度、限定日期、请假申请与文件整理").font(.system(size:11)).foregroundStyle(Palette.accent) }
            HStack(spacing:7) { Image(systemName:"lock");Text("全程在本机 · 整理文件先预览 · 统计后可以继续追问“那陈雨呢？”") }.font(.system(size:10)).foregroundStyle(Palette.muted)
        }.padding(.vertical,8)
    }
    private func conversationStarter(_ title:String,prompt:String,icon:String="bubble.left")->some View {
        Button { store.newTask(); store.prompt = prompt } label: {
            Label(title,systemImage:icon).font(.system(size:10)).foregroundStyle(Palette.accent)
                .padding(.horizontal,12).padding(.vertical,8).background(Palette.pale,in:Capsule())
        }.buttonStyle(.plain).disabled(store.contextLocked)
    }
    private func taskCard(_ task:OfficeExample)->some View {
        Button { store.useOfficeExample(task) } label: {
            HStack(alignment:.top,spacing:12) {
                Image(systemName:task.icon).font(.system(size:18,weight:.light)).foregroundStyle(Palette.accent).frame(width:31,height:35).background(Palette.pale,in:RoundedRectangle(cornerRadius:8))
                VStack(alignment:.leading,spacing:7) { Text(task.title).font(.system(size:12,weight:.medium)).foregroundStyle(Palette.ink);Text(task.prompt).font(.system(size:10)).foregroundStyle(Palette.muted).lineLimit(2).multilineTextAlignment(.leading) }
                Spacer(minLength:0);Image(systemName:"arrow.up.right").font(.system(size:10)).foregroundStyle(Palette.muted)
            }.padding(15).frame(maxWidth:.infinity,minHeight:76,alignment:.leading).background(.white,in:RoundedRectangle(cornerRadius:12)).overlay(RoundedRectangle(cornerRadius:12).stroke(Palette.line))
        }.buttonStyle(.plain).disabled(store.contextLocked)
    }
}
