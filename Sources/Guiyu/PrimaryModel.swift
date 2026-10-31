import Foundation

enum PrimaryModel {
    static let id = "qwen3.6-35b-a3b"
    static let name = "Qwen3.6 35B A3B"

    static func placeholder(storage: URL = ModelStorage.root) -> LocalModelOption {
        LocalModelOption(id:id,name:name,path:storage.appendingPathComponent("Installed/"+id).path,
                         architecture:"qwen3_5_moe",bytes:0,bits:4)
    }

    static func prepared(_ item: CatalogModel, storage: URL = ModelStorage.root) -> LocalModelOption? {
        for kind in ["Installed","Research"] {
            let directory=storage.appendingPathComponent(kind+"/"+item.id,isDirectory:true)
            guard let values=try? directory.resourceValues(forKeys:[.isSymbolicLinkKey]),values.isSymbolicLink != true,
                  let data=try? Data(contentsOf:directory.appendingPathComponent("guiyu-install.json")),
                  let marker=try? JSONDecoder().decode([String:String].self,from:data),
                  marker["revision"]==item.revision,
                  var model=try? LocalModelOption.inspect(directory),model.bytes>0 else { continue }
            let expected=item.files.filter { $0.name.hasSuffix(".safetensors") }.reduce(Int64(0)) { $0+$1.bytes }
            guard model.bytes==expected else { continue }
            model.id=item.id;model.name=item.name
            return model
        }
        return nil
    }

    // Replace the initial zero-byte download placeholder and deduplicate both
    // identity and path. A completed download must never leave a stale choice.
    static func merging(_ option: LocalModelOption, into models: [LocalModelOption]) -> [LocalModelOption] {
        [option]+models.filter { $0.id != option.id && $0.path != option.path }
    }
}
