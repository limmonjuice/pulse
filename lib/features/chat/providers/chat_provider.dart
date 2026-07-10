// lib/features/chat/providers/chat_provider.dart

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/message.dart';
import '../models/urgency_result.dart';
import '../repositories/callable_chat_repository.dart';
import '../repositories/chat_repository.dart';
import '../repositories/fixture_chat_repository.dart';

/// Flip to false to wire the real backend once fixture-mode UI review is
/// complete. Guarded by kDebugMode below so a release build can never
/// accidentally ship fixture mode regardless of this const's value.
const bool _useFixturesInDebug = true;

final chatRepositoryProvider = Provider<ChatRepository>((ref) {
  if (kDebugMode && _useFixturesInDebug) {
    return FixtureChatRepository();
  }
  return CallableChatRepository();
});

/// Holds the conversation's turn list. No Firestore persistence this
/// pass — conversation lives in memory only. TODO(episode model): once
/// conversations are persisted server-side, this becomes a stream over
/// the active episode's messages instead of local AsyncNotifier state.
class ChatController extends AsyncNotifier<List<Message>> {
  @override
  FutureOr<List<Message>> build() => <Message>[];

  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;

    final history = state.value ?? <Message>[];
    final withUser = [...history, Message.user(trimmed)];
    // Deliberately stays AsyncData (not AsyncLoading) while the request is
    // in flight: AsyncNotifier's public API has no supported way to build
    // an AsyncLoading that still exposes a previous value — the method
    // that does (`copyWithPrevious`) is `@internal` to package:riverpod as
    // of 3.x, and AGENTS.md requires a clean `flutter analyze`. Consumers
    // that need a "sending" indicator should track it separately rather
    // than reading `.isLoading` off this provider.
    state = AsyncData(withUser);

    final repository = ref.read(chatRepositoryProvider);
    try {
      final reply = await repository.send(text: trimmed, history: history);
      state = AsyncData([...withUser, reply]);
    } catch (_) {
      state = AsyncData([...withUser, _errorMessage()]);
    }
  }

  /// The error bubble's retry affordance: drops the failed exchange
  /// (the last user message and whatever followed it) and resends.
  Future<void> retryLast() async {
    final messages = state.value ?? <Message>[];
    final lastUserIndex = messages.lastIndexWhere(
      (m) => m.role == MessageRole.user,
    );
    if (lastUserIndex == -1) return;

    final text = messages[lastUserIndex].text;
    state = AsyncData(messages.sublist(0, lastUserIndex));
    await send(text);
  }

  /// Toggles one self-care checklist item for one assessment message.
  /// Session-only UI state — see Message.checkedSelfCare.
  void toggleSelfCare(String messageId, int index) {
    final messages = state.value;
    if (messages == null) return;
    state = AsyncData([
      for (final m in messages)
        if (m.id == messageId)
          m.copyWith(
            checkedSelfCare: m.checkedSelfCare.contains(index)
                ? (m.checkedSelfCare.toSet()..remove(index))
                : (m.checkedSelfCare.toSet()..add(index)),
          )
        else
          m,
    ]);
  }

  Message _errorMessage() => Message.assistant(
    const UrgencyResult(
      type: ChatTurnType.error,
      message:
          "Something's not working right on my end. I'm still here — "
          'try sending that again in a bit?',
    ),
  );
}

final chatControllerProvider =
    AsyncNotifierProvider<ChatController, List<Message>>(ChatController.new);
