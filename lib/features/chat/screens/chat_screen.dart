// lib/features/chat/screens/chat_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/app_router.dart';
import '../../../core/theme/app_theme.dart';
import '../models/message.dart';
import '../models/urgency_result.dart';
import '../providers/chat_provider.dart';
import '../widgets/assessment_card.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/chat_input_bar.dart';
import '../widgets/crisis_card.dart';
import '../widgets/error_bubble.dart';
import '../widgets/quick_reply_row.dart';
import '../widgets/typing_indicator.dart';
import '../widgets/urgency_strip.dart';

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  /// Approximate scroll to the most recent rendered card: item offsets
  /// aren't measurable in a plain ListView, so target the card's index as
  /// a fraction of the scroll extent — enough to bring the card on-screen
  /// without adding a scroll package (AGENTS.md: smallest useful version).
  void _scrollToLatestCard(List<Message> messages) {
    final index = messages.lastIndexWhere(
      (m) =>
          m.payload?.type == ChatTurnType.assessment &&
          (m.payload!.cardAction == CardAction.newCard ||
              m.payload!.cardAction == CardAction.update),
    );
    if (index == -1 || !_scrollController.hasClients) return;
    final denominator = messages.length > 1 ? messages.length - 1 : 1;
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent * index / denominator,
      duration: const Duration(milliseconds: 250),
      curve: Curves.easeOut,
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    // Only scroll when a turn was actually appended (list length grew),
    // not on every state change — chatControllerProvider also emits a
    // new state on toggleSelfCare() (checking a self-care box), which
    // uses the exact same provider. Without this guard, ticking a
    // checklist item on an AssessmentCard that isn't the last thing on
    // screen would yank the viewport to the bottom mid-interaction.
    // Found during Task 17 code review.
    ref.listen(chatControllerProvider, (previous, next) {
      final previousLength = previous?.value?.length ?? 0;
      final nextLength = next.value?.length ?? 0;
      if (nextLength > previousLength) _scrollToBottom();
    });
    final state = ref.watch(chatControllerProvider);
    final messages = state.value ?? const <Message>[];
    final hasVisitSummaryContent = messages.any(
      (m) =>
          m.payload?.type == ChatTurnType.assessment ||
          m.payload?.type == ChatTurnType.crisis,
    );
    // Not state.isLoading: see chatIsSendingProvider's doc comment in
    // chat_provider.dart for why (AsyncLoading.copyWithPrevious is
    // @internal in this Riverpod version, so chatControllerProvider's
    // own AsyncValue never actually enters a loading state).
    final isLoading = ref.watch(chatIsSendingProvider);
    final firstCrisisIndex = messages.indexWhere(
      (m) => m.payload?.type == ChatTurnType.crisis,
    );
    // Engine v2 (spec §9): the pinned strip is what makes "the person can
    // already see the card" true after it scrolls away. Server-driven —
    // the client applies no urgency logic of its own. Hidden in crisis
    // mode (the crisis UI owns the screen).
    final conversationState = ref.watch(activeConversationStateProvider);
    final stripNextStep = ref.watch(activeNextStepProvider);
    final showStrip =
        conversationState != null &&
        conversationState.assessmentActive &&
        conversationState.urgency != null &&
        firstCrisisIndex == -1;

    return Scaffold(
      backgroundColor: AppColors.bgCream,
      appBar: AppBar(
        backgroundColor: AppColors.bgCream,
        elevation: 0,
        title: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  colors: [AppColors.companionGradientLight, AppColors.primary],
                ),
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 12),
            Text(
              'Pulse',
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontSize: 16),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.summarize_outlined),
            tooltip: 'Visit summary',
            onPressed: hasVisitSummaryContent
                ? () => context.push(AppRoutes.visitSummary)
                : null,
          ),
        ],
      ),
      body: Column(
        children: [
          if (showStrip)
            UrgencyStrip(
              urgency: conversationState.urgency!,
              nextStep: stripNextStep,
              onTap: () => _scrollToLatestCard(messages),
            ),
          Expanded(
            child: ListView.separated(
              controller: _scrollController,
              padding: const EdgeInsets.all(18),
              itemCount: messages.length + (isLoading ? 1 : 0),
              separatorBuilder: (_, __) => const SizedBox(height: 9),
              itemBuilder: (context, index) {
                if (index >= messages.length) {
                  return const TypingIndicator();
                }
                return _buildTurn(messages[index], index, firstCrisisIndex);
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 16),
            child: ChatInputBar(
              enabled: !isLoading,
              onSend: (text) =>
                  ref.read(chatControllerProvider.notifier).send(text),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTurn(Message message, int index, int firstCrisisIndex) {
    if (message.role == MessageRole.user) {
      return ChatBubble(text: message.text, isUser: true);
    }

    final payload = message.payload;
    if (payload == null) {
      // Defensive only: every assistant Message in this codebase is built
      // via Message.assistant(payload), which always sets a non-null
      // payload (see message.dart) — there's currently no code path that
      // reaches this branch. Kept because Message.payload is legitimately
      // typed nullable at the model level (a future direct Message(...)
      // construction, e.g. from a persisted/rehydrated turn, could produce
      // one), and rendering the raw text as a plain bubble is a strictly
      // better failure mode here than a null-check crash.
      return ChatBubble(text: message.text, isUser: false);
    }

    switch (payload.type) {
      case ChatTurnType.crisis:
        if (index == firstCrisisIndex) {
          return CrisisCard(message: payload.message);
        }
        return ChatBubble(
          text: payload.message,
          isUser: false,
          softVariant: true,
        );
      case ChatTurnType.question:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ChatBubble(text: payload.message, isUser: false),
            if (payload.quickReplies.isNotEmpty) ...[
              const SizedBox(height: 9),
              QuickReplyRow(
                options: payload.quickReplies,
                onSelect: (option) =>
                    ref.read(chatControllerProvider.notifier).send(option),
              ),
            ],
          ],
        );
      case ChatTurnType.assessment:
        if (payload.cardAction != CardAction.newCard &&
            payload.cardAction != CardAction.update) {
          // The server said the visible guidance stands (keep/none):
          // render the text as a plain bubble — a duplicate card must
          // never resurrect the fire-alarm, whatever the payload claims.
          return ChatBubble(text: payload.message, isUser: false);
        }
        return AssessmentCard(
          result: payload,
          isUpdate: payload.cardAction == CardAction.update,
          checkedSelfCare: message.checkedSelfCare,
          onToggleSelfCare: (i) => ref
              .read(chatControllerProvider.notifier)
              .toggleSelfCare(message.id, i),
        );
      case ChatTurnType.conversation:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ChatBubble(text: payload.message, isUser: false),
            if (payload.quickReplies.isNotEmpty) ...[
              const SizedBox(height: 9),
              QuickReplyRow(
                options: payload.quickReplies,
                onSelect: (option) =>
                    ref.read(chatControllerProvider.notifier).send(option),
              ),
            ],
          ],
        );
      case ChatTurnType.error:
      case ChatTurnType.unparseable:
        return ErrorBubble(
          message: payload.message,
          onRetry: () => ref.read(chatControllerProvider.notifier).retryLast(),
        );
    }
  }
}
