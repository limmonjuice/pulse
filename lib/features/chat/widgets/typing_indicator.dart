import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The gentle "Pulse is thinking" indicator shown while awaiting a reply.
class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key});

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1400),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 15),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(AppRadii.chatBubble),
            topRight: Radius.circular(AppRadii.chatBubble),
            bottomRight: Radius.circular(AppRadii.chatBubble),
            bottomLeft: Radius.circular(AppRadii.chatBubbleTail),
          ),
          boxShadow: AppShadows.card,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) {
            return AnimatedBuilder(
              animation: _controller,
              builder: (context, child) {
                final t = (_controller.value + i * 0.2) % 1.0;
                final dy = -4 * (t < 0.5 ? t * 2 : (1 - t) * 2);
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 3),
                  child: Transform.translate(
                    offset: Offset(0, dy),
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        color: AppColors.primary,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                );
              },
            );
          }),
        ),
      ),
    );
  }
}
