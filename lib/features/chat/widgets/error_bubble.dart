// lib/features/chat/widgets/error_bubble.dart
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// The apologetic inline bubble for a degraded/unparseable reply, with a
/// tap-to-retry affordance that resends the last user message.
class ErrorBubble extends StatelessWidget {
  const ErrorBubble({super.key, required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Amber accent reused purely for its warm, non-alarming color — an
    // ErrorBubble is a parse/network failure, not a clinical urgency
    // signal. Do not read this as UrgencyLevel.seeDoctorSoon triage.
    final honey = theme.extension<UrgencyColors>()!.seeDoctorSoon;

    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        // sizeOf, not MediaQuery.of(context).size — see Task 10's
        // ChatBubble for why.
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.88,
        ),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(AppRadii.chatBubble),
              topRight: const Radius.circular(AppRadii.chatBubble),
              bottomRight: const Radius.circular(AppRadii.chatBubble),
              bottomLeft: const Radius.circular(AppRadii.chatBubbleTail),
            ),
            boxShadow: AppShadows.card,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 24,
                height: 24,
                margin: const EdgeInsets.only(top: 1),
                decoration: BoxDecoration(
                  color: honey.tint,
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.error_outline, size: 14, color: honey.text),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(message, style: theme.textTheme.bodyMedium),
                    const SizedBox(height: 8),
                    InkWell(
                      onTap: onRetry,
                      borderRadius: BorderRadius.circular(
                        AppRadii.buttonInCard,
                      ),
                      child: ConstrainedBox(
                        // Genuinely hit AppSpacing.minTouchTarget (44),
                        // not just an incremental improvement — this is
                        // a retry-after-failure affordance, arguably
                        // higher-stakes to get right than an ordinary
                        // link. Found during Task 13 code review.
                        constraints: const BoxConstraints(
                          minHeight: AppSpacing.minTouchTarget,
                        ),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                            'Tap to try again',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: AppColors.primaryInk,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
