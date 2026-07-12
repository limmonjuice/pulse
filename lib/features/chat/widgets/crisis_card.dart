// lib/features/chat/widgets/crisis_card.dart
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/constants/crisis_resources.dart';
import '../../../core/theme/app_theme.dart';

/// The crisis card: teal-tint, spacious, deliberately no tier machinery.
/// Message text, then a "Someone to talk to" resource list rendered from
/// the app-side crisisResources constant, tap-to-dial via url_launcher.
class CrisisCard extends StatelessWidget {
  const CrisisCard({
    super.key,
    required this.message,
    this.launcher = launchUrl,
  });

  final String message;

  /// Injectable so widget tests don't hit the real url_launcher plugin.
  final Future<bool> Function(Uri) launcher;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      // 22 is exactly AppSpacing.cardPaddingMax — use the token, not the
      // literal, matching AssessmentCard's own use of the same constant.
      padding: const EdgeInsets.all(AppSpacing.cardPaddingMax),
      decoration: BoxDecoration(
        color: AppColors.tintTeal,
        borderRadius: BorderRadius.circular(AppRadii.crisisCard),
        boxShadow: AppShadows.crisisCard,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      AppColors.companionGradientLight,
                      AppColors.primary,
                    ],
                  ),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  "I'm really glad you told me",
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontSize: 16,
                    color: AppColors.crisisHeading,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            message,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontSize: 15,
              height: 1.62,
              color: AppColors.crisisBody,
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Divider(
              height: 1,
              // Mockup divider is primaryInk at ~16% opacity (#293F7A86) —
              // withAlpha(0x29) reproduces that exact byte rather than
              // hardcoding a new standalone hex value.
              color: AppColors.primaryInk.withAlpha(0x29),
            ),
          ),
          Text(
            'Someone to talk to',
            style: theme.textTheme.titleSmall?.copyWith(
              color: AppColors.primaryInk,
            ),
          ),
          const SizedBox(height: 11),
          for (final resource in crisisResources) ...[
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Text(
                resource.name,
                style: theme.textTheme.titleMedium?.copyWith(fontSize: 14.5),
              ),
            ),
            for (final contact in resource.contacts)
              Padding(
                padding: const EdgeInsets.only(bottom: 9),
                child: _ContactRow(contact: contact, launcher: launcher),
              ),
          ],
          const SizedBox(height: 4),
          Text(
            "No pressure at all. I'll still be here whenever you want to keep talking.",
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(
              color: AppColors.crisisFooterText,
            ),
          ),
        ],
      ),
    );
  }
}

/// One tappable way to reach a [CrisisResource] — a call, text, or email
/// contact. Icon and launch scheme (tel:/sms:/mailto:) vary by
/// [CrisisContact.type]; visual treatment is identical across all three.
class _ContactRow extends StatelessWidget {
  const _ContactRow({required this.contact, required this.launcher});

  final CrisisContact contact;
  final Future<bool> Function(Uri) launcher;

  static const _icons = {
    ContactType.call: Icons.phone_outlined,
    ContactType.text: Icons.sms_outlined,
    ContactType.email: Icons.email_outlined,
  };

  // What to call the app that failed to open, in the fallback message —
  // "dialer" for a phone call reads oddly for an SMS or email attempt.
  static const _appNouns = {
    ContactType.call: 'dialer',
    ContactType.text: 'messages',
    ContactType.email: 'email app',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final display = contact.label == null
        ? contact.value
        : '${contact.value} (${contact.label})';

    return InkWell(
      // Note: 18 doesn't map to an existing AppRadii token (the closest
      // named row radii are cardRowRadius/14 and pillRowRadius/13 from
      // AssessmentCard's rows) — left as an inline literal rather than
      // reusing a visually-different value; a real gap worth tokenizing
      // in a follow-up pass alongside the rest of §8.
      borderRadius: BorderRadius.circular(18),
      // This is the single highest-stakes tap target in the whole
      // feature — a hotline row for a user the app has just flagged as
      // possibly in crisis. A silent no-op if launchUrl returns false
      // (no matching app) or throws (platform exception) is the worst
      // failure mode to leave unhandled here — fall back to a visible
      // message with the contact spelled out rather than fire-and-forget.
      onTap: () async {
        var launched = false;
        try {
          launched = await launcher(contact.uri);
        } catch (_) {
          launched = false;
        }
        if (!launched && context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              backgroundColor: AppColors.primaryDeep,
              content: Text(
                "Couldn't open your ${_appNouns[contact.type]}. $display.",
              ),
            ),
          );
        }
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(18),
          boxShadow: AppShadows.card,
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: const BoxDecoration(
                color: AppColors.tintTeal,
                shape: BoxShape.circle,
              ),
              child: Icon(
                _icons[contact.type],
                color: AppColors.primaryInk,
                size: 19,
              ),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Text(
                display,
                style: theme.textTheme.titleMedium?.copyWith(fontSize: 14.5),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
