// lib/features/chat/widgets/chat_input_bar.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The message input pill: text field with a 2000-char client-side cap
/// (matching functions/main.py's MAX_MESSAGE_LENGTH), a friendly counter
/// shown only near the limit, a mic icon (TODO: visual only this pass —
/// no voice input yet), and a circular send button.
class ChatInputBar extends StatefulWidget {
  const ChatInputBar({super.key, required this.onSend, this.enabled = true});

  final ValueChanged<String> onSend;
  final bool enabled;

  @override
  State<ChatInputBar> createState() => _ChatInputBarState();
}

class _ChatInputBarState extends State<ChatInputBar> {
  static const _maxLength = 2000;
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    if (!widget.enabled) return;
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    widget.onSend(text);
    setState(_controller.clear);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final remaining = _maxLength - _controller.text.length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        // Fixed-height slot (not a conditionally-inserted sibling): this
        // widget sits directly above the scrolling transcript's Expanded
        // ListView in Task 17's Column, so if the counter's presence
        // changed ChatInputBar's total height, the transcript viewport
        // would instantly snap taller/shorter the moment a message
        // crosses 1800 chars — jarring mid-typing. AnimatedOpacity keeps
        // the height constant and fades the text in/out instead. Found
        // during Task 16 code review.
        SizedBox(
          height: 20,
          child: Align(
            alignment: Alignment.centerRight,
            child: Padding(
              padding: const EdgeInsets.only(right: 8, bottom: 4),
              child: AnimatedOpacity(
                opacity: remaining <= 200 ? 1 : 0,
                duration: const Duration(milliseconds: 150),
                child: Text(
                  '$remaining left',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: remaining <= 0
                        ? AppColors.crisisFooterText
                        : AppColors.textFaint,
                  ),
                ),
              ),
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.fromLTRB(18, 8, 8, 8),
          decoration: BoxDecoration(
            color: AppColors.surface,
            // inputBar, not the generic pill token — the design doc
            // specifies a fixed 22px radius here, distinct from the
            // 999px stadium used for chips/badges. Found during code
            // review: with maxLines: 4, a true 999 stadium and a fixed
            // 22px corner look different once the field grows.
            borderRadius: BorderRadius.circular(AppRadii.inputBar),
            boxShadow: AppShadows.card,
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  maxLength: _maxLength,
                  enabled: widget.enabled,
                  minLines: 1,
                  maxLines: 4,
                  onChanged: (_) => setState(() {}),
                  onSubmitted: (_) => _submit(),
                  buildCounter:
                      (
                        _, {
                        required currentLength,
                        required isFocused,
                        maxLength,
                      }) => null,
                  decoration: InputDecoration(
                    border: InputBorder.none,
                    isDense: true,
                    hintText: 'Message Pulse…',
                    hintStyle: theme.textTheme.bodyMedium?.copyWith(
                      color: AppColors.textFaintAlt,
                    ),
                  ),
                ),
              ),
              // Mic — TODO: visual only this pass, wire voice input later.
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 6),
                child: Icon(Icons.mic_none_rounded, color: AppColors.primary),
              ),
              InkWell(
                onTap: widget.enabled ? _submit : null,
                borderRadius: BorderRadius.circular(21),
                child: Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    // Dimmed when disabled so the button doesn't look
                    // tappable while chatIsSendingProvider is true and
                    // onTap is silently null — found during Task 16
                    // code review (Task 17 wires enabled: !isLoading).
                    color: widget.enabled
                        ? AppColors.primaryDeep
                        : AppColors.primaryDeep.withValues(alpha: 0.4),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.arrow_upward_rounded,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
