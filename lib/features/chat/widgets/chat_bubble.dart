import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The plain user/Pulse bubble pair. [softVariant] is the teal-tint,
/// all-round-radius, no-tail style used for Pulse messages after a
/// conversation is crisis-locked (see chat_screen.dart's rendering rule —
/// only Pulse messages get this treatment, matching the task's explicit
/// scope).
class ChatBubble extends StatelessWidget {
  const ChatBubble({
    super.key,
    required this.text,
    required this.isUser,
    this.softVariant = false,
  });

  final String text;
  final bool isUser;
  final bool softVariant;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final BoxDecoration decoration = softVariant
        ? BoxDecoration(
            color: AppColors.tintTeal,
            // Spec: "all-round-24" for the soft crisis-locked Pulse
            // bubble — AppRadii.card (24), not AppRadii.chatBubble (22).
            borderRadius: BorderRadius.circular(AppRadii.card),
          )
        : BoxDecoration(
            color: isUser ? AppColors.primary : AppColors.surface,
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(AppRadii.chatBubble),
              topRight: const Radius.circular(AppRadii.chatBubble),
              bottomLeft: Radius.circular(
                isUser ? AppRadii.chatBubble : AppRadii.chatBubbleTail,
              ),
              bottomRight: Radius.circular(
                isUser ? AppRadii.chatBubbleTail : AppRadii.chatBubble,
              ),
            ),
            boxShadow: isUser ? AppShadows.userBubble : AppShadows.card,
          );

    // User bubble text is now AppColors.text, not Colors.white —
    // white-on-primary measured ~2.64:1, failing WCAG AA (4.5:1 needed at
    // this bodyMedium size/weight). AppColors.text on the unchanged teal
    // fill measures ~4.08:1: a large improvement, but still short of
    // 4.5:1 for normal-size text (it does clear the AA large-text/
    // UI-component 3:1 bar). Flagged, not silently resolved further — see
    // PULSE_DESIGN_SYSTEM.md's chat-bubble entry.
    final Color textColor = softVariant ? AppColors.crisisBody : AppColors.text;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        // sizeOf (not MediaQuery.of(context).size) scopes the rebuild
        // dependency to just the size field — MediaQuery.of would
        // rebuild every bubble in the list on keyboard open/close too.
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.78,
        ),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 12),
          decoration: decoration,
          child: Text(
            text,
            style: theme.textTheme.bodyMedium?.copyWith(color: textColor),
          ),
        ),
      ),
    );
  }
}
