import Foundation

@main struct ModelPreparationProbe {
    static func main() throws {
        precondition(CommandLine.arguments.count == 3)
        let catalogURL = URL(fileURLWithPath:CommandLine.arguments[1])
        let directory = URL(fileURLWithPath:CommandLine.arguments[2],isDirectory:true)
        let catalog = try JSONDecoder().decode([CatalogModel].self,from:Data(contentsOf:catalogURL))
        let advanced = catalog.first { $0.id == "qwen3.6-35b-a3b" }!
        let marker = try JSONDecoder().decode([String:String].self,from:Data(contentsOf:directory.appendingPathComponent("guiyu-install.json")))
        precondition(marker["revision"] == advanced.revision)
        let model = try LocalModelOption.inspect(directory)
        precondition(model.architecture == "qwen3_5_moe" && model.bits == 4)
        precondition(model.bytes == advanced.files.filter { $0.name.hasSuffix(".safetensors") }.reduce(0) { $0 + $1.bytes })
        precondition(DevicePolicy.allows(model,memoryBytes:32*1024*1024*1024))
        precondition(!DevicePolicy.allows(model,memoryBytes:24*1024*1024*1024))
        let choices = catalog.filter { !$0.isEmbedding && !$0.isPrivacy && ($0.recommended == true || $0.advanced == true) }
        precondition(choices.map(\.id) == ["qwen3.6-35b-a3b"])
        let selected=PrimaryModel.prepared(advanced)!
        precondition(selected.id==PrimaryModel.id && selected.path==directory.path)
        let merged=PrimaryModel.merging(selected,into:[PrimaryModel.placeholder(),selected])
        precondition(merged.count==1 && merged[0].bytes==model.bytes)
        let report:[String:Any] = ["status":"PASS_NATIVE_MODEL_METADATA_AND_ADMISSION","catalog_revision":advanced.revision,
                                  "model":advanced.name,"weight_bytes":model.bytes,"architecture":model.architecture,
                                  "primary_default":PrimaryModel.id,"placeholder_replaced":true,"research_marker_matches":true,"admitted_on32GB":true,"rejected_on24GB":true,
                                  "discovery_choices":choices.map(\.name),"gui_verified":false,
                                  "scope":"Native catalog decoding, actual local-model inspection and memory policy; no UI click or history access."]
        print(String(decoding:try JSONSerialization.data(withJSONObject:report,options:[.sortedKeys]),as:UTF8.self))
    }
}
