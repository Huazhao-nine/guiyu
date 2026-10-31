import AppKit
@main struct MessageEditorChecks {
    @MainActor static func main() {
        _ = NSApplication.shared
        let view=MessageTextView(frame:NSRect(x:0,y:0,width:400,height:70))
        var sent=0;view.submit={sent+=1};view.string="测试消息"
        func key(_ flags:NSEvent.ModifierFlags=[],repeatKey:Bool=false)->NSEvent {
            NSEvent.keyEvent(with:.keyDown,location:.zero,modifierFlags:flags,timestamp:0,windowNumber:0,context:nil,characters:"\r",charactersIgnoringModifiers:"\r",isARepeat:repeatKey,keyCode:36)!
        }
        view.keyDown(with:key());precondition(sent==1 && view.string=="测试消息")
        view.keyDown(with:key(.command));precondition(sent==2)
        view.keyDown(with:key([],repeatKey:true));precondition(sent==2)
        view.setSelectedRange(NSRange(location:(view.string as NSString).length,length:0))
        view.keyDown(with:key(.shift));precondition(sent==2 && view.string.contains("\n"))
        view.setMarkedText("归屿",selectedRange:NSRange(location:2,length:0),replacementRange:NSRange(location:NSNotFound,length:0))
        precondition(view.hasMarkedText());view.keyDown(with:key());precondition(sent==2)
        print("MESSAGE_EDITOR_PASS: Return sends, Shift+Return inserts newline, Cmd+Return remains compatible, key repeat ignored, marked input never submits")
    }
}
