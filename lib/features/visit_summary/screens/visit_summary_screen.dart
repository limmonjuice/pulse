// lib/features/visit_summary/screens/visit_summary_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../../../shared/widgets/checklist_row.dart';
import '../../../shared/widgets/warning_pill.dart';
import '../../chat/providers/chat_provider.dart';
import '../models/visit_summary_facts.dart';
import '../providers/visit_summary_provider.dart';

const Map<UrgencyLevel, String> _tierLabel = {
  UrgencyLevel.monitorAtHome: 'Monitor at home',
  UrgencyLevel.seeDoctorSoon: 'See a doctor soon',
  UrgencyLevel.seekCareNow: 'Seek care now',
};

class VisitSummaryScreen extends ConsumerWidget {
  const VisitSummaryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final messages = ref.watch(chatControllerProvider).value ?? const [];
    final facts = VisitSummaryFacts.fromMessages(messages);
    final narrativeState = ref.watch(visitSummaryControllerProvider);
    final currentLastId = messages.isEmpty ? '' : messages.last.id;
    final isStale =
        narrativeState.value != null &&
        narrativeState.value!.generatedAtMessageId != currentLastId;

    void onGenerate() => ref
        .read(visitSummaryControllerProvider.notifier)
        .generate(messages: messages, finalUrgency: facts.finalUrgency);

    return Scaffold(
      backgroundColor: AppColors.bgCream,
      appBar: AppBar(
        backgroundColor: AppColors.bgCream,
        elevation: 0,
        title: const Text('Visit summary'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        children: [
          _Header(facts: facts),
          const SizedBox(height: AppSpacing.sectionGap),
          _NarrativeBlock(
            state: narrativeState,
            isStale: isStale,
            onGenerate: onGenerate,
          ),
          if (facts.findings.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sectionGap),
            Text('What was discussed', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final f in facts.findings) ChecklistRow(text: f),
          ],
          if (facts.selfCare.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sectionGap),
            Text('Self-care already suggested', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            // Read-only here — no per-item identity to back a checked
            // state across turns (design spec §5.3).
            for (final s in facts.selfCare) ChecklistRow(text: s),
          ],
          if (facts.monitoring.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sectionGap),
            Text('Things to monitor', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final m in facts.monitoring) ChecklistRow(text: m),
          ],
          if (facts.watchFor.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sectionGap),
            Text('Get care if…', style: theme.textTheme.titleSmall),
            const SizedBox(height: 9),
            for (final w in facts.watchFor) WarningPill(text: w),
          ],
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.facts});
  final VisitSummaryFacts facts;

  @override
  Widget build(BuildContext context) {
    // Tier badge and crisis-mention line render independently, not
    // either/or (design spec §5.3) — a real assessment and a later
    // crisis moment can both be true of the same conversation.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (facts.finalUrgency != null)
          _TierBadge(
            urgency: facts.finalUrgency!,
            progressionLabel: facts.urgencyChanged
                ? 'Started at ${_tierLabel[facts.initialUrgency]}, now '
                      '${_tierLabel[facts.finalUrgency]}'
                : null,
          ),
        if (facts.hadCrisisTurn) ...[
          if (facts.finalUrgency != null) const SizedBox(height: 12),
          _CrisisMentionBanner(text: facts.crisisMentionText!),
        ],
      ],
    );
  }
}

class _TierBadge extends StatelessWidget {
  const _TierBadge({required this.urgency, required this.progressionLabel});
  final UrgencyLevel urgency;
  final String? progressionLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final palette = theme.extension<UrgencyColors>()!.forLevel(urgency);
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPaddingMax),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadii.card),
        boxShadow: AppShadows.card,
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: palette.solid,
              borderRadius: BorderRadius.circular(AppRadii.iconChip),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _tierLabel[urgency]!,
                  style: theme.textTheme.titleLarge?.copyWith(color: palette.text),
                ),
                if (progressionLabel != null) ...[
                  const SizedBox(height: 4),
                  Text(progressionLabel!, style: theme.textTheme.bodySmall),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _CrisisMentionBanner extends StatelessWidget {
  const _CrisisMentionBanner({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPaddingMin),
      decoration: BoxDecoration(
        color: AppColors.tintTeal,
        borderRadius: BorderRadius.circular(AppRadii.card),
      ),
      child: Text(text, style: Theme.of(context).textTheme.bodyMedium),
    );
  }
}

class _NarrativeBlock extends StatelessWidget {
  const _NarrativeBlock({
    required this.state,
    required this.isStale,
    required this.onGenerate,
  });

  final AsyncValue<VisitSummaryState?> state;
  final bool isStale;
  final VoidCallback onGenerate;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (state.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (state.hasError) {
      return _NarrativeError(onRetry: onGenerate);
    }
    final data = state.value;
    if (data == null) {
      return _GenerateCta(onGenerate: onGenerate);
    }
    if (isStale) {
      return _StaleBanner(onRegenerate: onGenerate);
    }
    if (data.result.isError) {
      return _NarrativeError(onRetry: onGenerate, message: data.result.errorMessage);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(data.result.summary, style: theme.textTheme.bodyMedium),
        if (data.result.questionsForDoctor.isNotEmpty) ...[
          const SizedBox(height: 18),
          Text('Questions to ask your doctor', style: theme.textTheme.titleSmall),
          const SizedBox(height: 9),
          for (final q in data.result.questionsForDoctor) ChecklistRow(text: q),
        ],
      ],
    );
  }
}

class _GenerateCta extends StatelessWidget {
  const _GenerateCta({required this.onGenerate});
  final VoidCallback onGenerate;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton(
        onPressed: onGenerate,
        child: const Text('Generate summary'),
      ),
    );
  }
}

class _NarrativeError extends StatelessWidget {
  const _NarrativeError({required this.onRetry, this.message});
  final VoidCallback onRetry;
  final String? message;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          message ?? "Couldn't put together a visit summary right now.",
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 9),
        TextButton(onPressed: onRetry, child: const Text('Try again')),
      ],
    );
  }
}

class _StaleBanner extends StatelessWidget {
  const _StaleBanner({required this.onRegenerate});
  final VoidCallback onRegenerate;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'The conversation has continued since this summary was generated.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 9),
        TextButton(onPressed: onRegenerate, child: const Text('Regenerate')),
      ],
    );
  }
}
