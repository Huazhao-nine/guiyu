import AppKit
import SwiftUI

// Handle Return in the text view, after checking the input method's marked
// range. A global Return shortcut would also consume Chinese candidate commits.
class MessageTextView:NSTextView {
    var submit:()->Void = {}
    var focusChanged:(Bool)->Void = { _ in }
    override func keyDown(with event:NSEvent) {
        let modifiers=event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        let isReturn=event.keyCode==36 || event.keyCode==76
        if isReturn && !hasMarkedText() && modifiers.intersection([.shift,.option,.control]).isEmpty {
            if !event.isARepeat { submit() }
            return
        }
        super.keyDown(with:event)
    }
    override func becomeFirstResponder()->Bool {
        let accepted=super.becomeFirstResponder()
        if accepted { focusChanged(true) }
        return accepted
    }
    override func resignFirstResponder()->Bool {
        let accepted=super.resignFirstResponder()
        if accepted { focusChanged(false) }
        return accepted
    }
}

struct MessageEditor:NSViewRepresentable {
    @Binding var text:String
    @Binding var focused:Bool
    var editable:Bool
    var canSubmit:Bool
    var onSubmit:()->Void
    final class Coordinator:NSObject,NSTextViewDelegate {
        var parent:MessageEditor
        init(_ parent:MessageEditor) { self.parent=parent }
        func textDidChange(_ notification:Notification) {
            guard let view=notification.object as? NSTextView else { return }
            parent.text=view.string
        }
    }
    func makeCoordinator()->Coordinator { Coordinator(self) }
    func makeNSView(context:Context)->NSScrollView {
        let scroll=NSScrollView(),view=MessageTextView()
        scroll.drawsBackground=false;scroll.borderType = .noBorder
        scroll.hasVerticalScroller=true;scroll.autohidesScrollers=true
        view.isRichText=false;view.importsGraphics=false;view.drawsBackground=false
        view.font = .systemFont(ofSize:13);view.textColor = .labelColor
        view.textContainerInset=NSSize(width:4,height:6)
        view.isVerticallyResizable=true;view.isHorizontallyResizable=false
        view.autoresizingMask=[.width];view.textContainer?.widthTracksTextView=true
        view.minSize=NSSize(width:0,height:70);view.maxSize=NSSize(width:CGFloat.greatestFiniteMagnitude,height:CGFloat.greatestFiniteMagnitude)
        view.frame=NSRect(x:0,y:0,width:scroll.contentSize.width,height:70)
        view.setAccessibilityLabel("消息输入框")
        view.delegate=context.coordinator;scroll.documentView=view
        return scroll
    }
    func updateNSView(_ scroll:NSScrollView,context:Context) {
        guard let view=scroll.documentView as? MessageTextView else { return }
        context.coordinator.parent=self
        if view.string != text && !view.hasMarkedText() {
            let selection=view.selectedRange();view.string=text
            let end=(text as NSString).length
            view.setSelectedRange(NSRange(location:min(selection.location,end),length:0))
        }
        view.isEditable=editable
        view.submit={ if canSubmit { onSubmit() } }
        view.focusChanged={ value in
            DispatchQueue.main.async { if focused != value { focused=value } }
        }
        if focused && editable && view.window?.firstResponder !== view {
            DispatchQueue.main.async { [weak view] in
                guard let view,view.isEditable else { return }
                view.window?.makeFirstResponder(view)
            }
        }
    }
}
