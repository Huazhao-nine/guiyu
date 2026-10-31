import SwiftUI

struct QueryBuilderView: View {
    @EnvironmentObject var store: Store
    @ViewState private var query = TableQuery()
    private let operations = [("eq","等于"),("ne","不等于"),("contains","包含"),("not_contains","不包含"),("gt","大于"),("gte","不少于"),("lt","小于"),("lte","不超过")]
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack {
                Image(systemName:"line.3.horizontal.decrease.circle").font(.system(size:24,weight:.light)).foregroundStyle(Palette.accent)
                VStack(alignment:.leading,spacing:5) { Text("把范围说清楚").font(.custom("Songti SC",size:25)); Text("先选条件，再看匹配记录和统计结果。").font(.system(size:11)).foregroundStyle(Palette.muted) }
                Spacer(); Button { store.showQueryBuilder = false } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(Palette.muted) }.buttonStyle(.plain)
            }
            if store.schemaLoading {
                HStack(spacing:10) { ProgressView().controlSize(.small); Text("正在读取表头与当前条件…").font(.system(size:12)) }.frame(maxWidth:.infinity,minHeight:220)
            } else if store.schemaColumns.isEmpty {
                VStack(alignment:.leading,spacing:13) {
                    Text("先准备一张表格").font(.system(size:16,weight:.medium))
                    Text("可以添加 CSV 或 Excel，也可以先从文档中提取表格，再来设置条件。").font(.system(size:12)).foregroundStyle(Palette.muted).lineSpacing(5)
                    Button("从当前资料提取表格") { store.showQueryBuilder = false; store.chooseTemplate(.table) }.buttonStyle(.bordered)
                }.frame(maxWidth:.infinity,minHeight:190,alignment:.leading)
            } else {
                HStack { Text("\(store.schemaRowCount) 行原始数据 · \(store.schemaColumns.count) 个字段").font(.system(size:11)).foregroundStyle(Palette.muted); Spacer(); Button("清除条件") { query.rules = [] }.font(.system(size:11)).buttonStyle(.plain).foregroundStyle(Palette.accent) }
                ScrollView {
                    VStack(alignment:.leading,spacing:13) {
                        Picker("条件关系",selection:$query.match) { Text("全部满足").tag("all"); Text("任一满足").tag("any") }.pickerStyle(.segmented).frame(width:230)
                        if query.rules.isEmpty { Text("当前使用全部记录。添加条件后，只对匹配行进行统计。").font(.system(size:11)).foregroundStyle(Palette.muted).padding(.vertical,17) }
                        ForEach($query.rules) { $rule in
                            HStack(spacing:8) {
                                Picker("字段",selection:$rule.column) { ForEach(store.schemaColumns,id:\.self) { Text($0).tag($0) } }.labelsHidden().frame(width:155)
                                Picker("比较方式",selection:$rule.operation) { ForEach(operations,id:\.0) { Text($0.1).tag($0.0) } }.labelsHidden().frame(width:100)
                                TextField("比较值",text:$rule.value).textFieldStyle(.roundedBorder).frame(minWidth:120)
                                Menu { ForEach(store.schemaValues[rule.column] ?? [],id:\.self) { value in Button(value) { rule.value = value } } } label: { Image(systemName:"chevron.down").font(.system(size:10)) }.menuStyle(.borderlessButton).frame(width:17).help("从已有值选择")
                                Button { query.rules.removeAll { $0.id == rule.id } } label: { Image(systemName:"minus.circle").foregroundStyle(Palette.muted) }.buttonStyle(.plain).help("移除这个条件")
                            }.padding(10).background(.white,in:RoundedRectangle(cornerRadius:10)).overlay(RoundedRectangle(cornerRadius:10).stroke(Palette.line))
                        }
                        Button { var rule = QueryRule(); rule.column = store.schemaColumns.first ?? ""; query.rules.append(rule) } label: { Label("添加条件",systemImage:"plus") }.buttonStyle(.plain).font(.system(size:11)).foregroundStyle(Palette.accent).disabled(query.rules.count>=8)
                        Divider().padding(.vertical,8)
                        HStack { Text("分组方式").font(.system(size:12,weight:.medium)); Spacer(); Picker("分组字段",selection:$query.groupBy) { Text("不分组").tag(""); ForEach(store.schemaColumns,id:\.self) { Text("按"+$0+"分组").tag($0) } }.labelsHidden().frame(width:230) }
                        HStack { Text("统计字段").font(.system(size:12,weight:.medium)); Spacer(); Picker("统计字段",selection:$query.metric) { Text("全部数值字段").tag(""); ForEach(store.schemaNumericColumns,id:\.self) { Text($0).tag($0) } }.labelsHidden().frame(width:230) }
                        Text("大小比较支持数值和 YYYY-MM-DD 日期。原始数据会保留，下一轮可以换条件重新计算。").font(.system(size:10)).foregroundStyle(Palette.muted).lineSpacing(5).padding(.top,9)
                    }
                }.frame(minHeight:285,maxHeight:390)
            }
            if let error = store.errorMessage { Text(error).font(.system(size:11)).foregroundStyle(Palette.warm).lineSpacing(4) }
            HStack {
                Text("本地筛选 · 本地计算").font(.system(size:10)).foregroundStyle(Palette.muted)
                Spacer(); Button("取消") { store.showQueryBuilder = false }.buttonStyle(.plain).foregroundStyle(Palette.muted)
                Button { store.applyFilters(query) } label: { Text("查看筛选计划").font(.system(size:12,weight:.medium)).padding(.horizontal,18).padding(.vertical,11).foregroundStyle(.white).background(Palette.accent,in:RoundedRectangle(cornerRadius:9)) }.buttonStyle(.plain).disabled(store.schemaLoading || store.schemaColumns.isEmpty || query.rules.contains { $0.value.trimmingCharacters(in:.whitespaces).isEmpty })
            }
        }.padding(30).frame(width:710).background(Palette.background)
        .onAppear { query = store.schemaQuery }
        .onChange(of:store.schemaLoading) { _,loading in if !loading { query = store.schemaQuery } }
    }
}

struct PreviousTurnView: View {
    let record: TaskRecord
    @ViewState private var expanded = false
    var body: some View {
        VStack(alignment:.leading,spacing:11) {
            Button { withAnimation { expanded.toggle() } } label: {
                HStack(spacing:10) { Image(systemName:"bubble.left.and.text.bubble.right").foregroundStyle(Palette.accent); Text(record.prompt).font(.system(size:11)).lineLimit(2).multilineTextAlignment(.leading); Spacer(); Image(systemName:expanded ? "chevron.up" : "chevron.down").font(.system(size:9)).foregroundStyle(Palette.muted) }
            }.buttonStyle(.plain)
            if expanded { MarkdownText(text:record.text) }
            else if let summary = record.querySummary, !summary.isEmpty { Text(summary).font(.system(size:10)).foregroundStyle(Palette.muted).lineLimit(2) }
        }.padding(15).background(Palette.sidebar.opacity(0.45),in:RoundedRectangle(cornerRadius:12)).overlay(RoundedRectangle(cornerRadius:12).stroke(Palette.line.opacity(0.6)))
    }
}

struct SearchResultsView: View {
    @EnvironmentObject var store: Store
    let hits: [SearchHit]
    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            HStack { Label("匹配原文",systemImage:"doc.text.magnifyingglass").font(.system(size:12,weight:.medium)); Spacer(); Button("仅用这些资料继续") { store.useSearchHits(hits) }.buttonStyle(.plain).font(.system(size:10)).foregroundStyle(Palette.accent).disabled(store.isBusy) }
            ForEach(hits) { hit in
                VStack(alignment:.leading,spacing:8) {
                    HStack { Text(hit.name).font(.system(size:12,weight:.medium)); Spacer(); Text("\(hit.id) · 第\(hit.line)行").font(.system(size:9)).foregroundStyle(Palette.muted) }
                    Text(hit.snippet).font(.system(size:11)).foregroundStyle(Palette.ink.opacity(0.85)).lineSpacing(5).textSelection(.enabled)
                    Button("查看这段原文") { store.previewSource = SourceDoc(["id":hit.id,"name":hit.name,"path":hit.path,"preview":hit.snippet]) }.buttonStyle(.plain).font(.system(size:10)).foregroundStyle(Palette.accent)
                }.padding(15).background(.white,in:RoundedRectangle(cornerRadius:12)).overlay(RoundedRectangle(cornerRadius:12).stroke(Palette.line))
            }
        }
    }
}
