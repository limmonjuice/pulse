// lib/features/chat/providers/chat_provider.dart

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// StateProvider moved to the "legacy" surface in Riverpod 3.x — not
// exported from the main flutter_riverpod.dart barrel. Confirmed by
// reading flutter_riverpod-3.3.2/lib/legacy.dart directly.
import 'package:flutter_riverpod/legacy.dart' show StateProvider;

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

/// Whether a send is currently in flight — drives the typing indicator
/// in ChatScreen (Task 17). A plain flag, not part of chatControllerProvider's
/// own AsyncValue: Riverpod 3.x's `AsyncLoading().copyWithPrevious(...)`
/// (the framework's own mechanism for "loading, but keep showing the
/// previous value") is `@internal` to package:riverpod as of 3.3.2 — not
/// callable from application code, confirmed by reading
/// riverpod-3.3.2/lib/src/core/async_value.dart directly. Without it,
/// there's no way to make chatControllerProvider's AsyncValue report
/// `isLoading` while still exposing the in-progress message list, so
/// this narrow, deliberately-scoped exception to AGENTS.md's "not manual
/// isLoading booleans" guidance exists only because the framework's own
/// intended mechanism isn't reachable here.
final chatIsSendingProvider = StateProvider<bool>((ref) => false);

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
    // Re-entrancy guard: without this, two overlapping sends (a double
    // tap before the UI's `enabled: !isLoading` gate takes effect on the
    // next frame, or retryLast() racing a fresh send()) can each capture
    // their own stale `withUser` snapshot and silently clobber each
    // other's result when their awaits resolve out of order — found
    // during Task 9 code review, not hypothetical.
    if (ref.read(chatIsSendingProvider)) return;

    final history = state.value ?? <Message>[];
    final withUser = [...history, Message.user(trimmed)];
    state = AsyncData(withUser);

    // Everything from here through the reply/error assignment must stay
    // inside the try — including resolving the repository — so ANY
    // exception on this path (not just ones thrown by repository.send()
    // itself) still hits the catch/finally below. A prior version read
    // `ref.read(chatRepositoryProvider)` above the try; if that read
    // ever threw, chatIsSendingProvider would stay stuck `true` forever
    // (permanently disabling the input) and the exception would become
    // an unhandled Future rejection, since the planned call site
    // (`onSend: (text) => ref.read(...).send(text)`) never awaits this
    // Future. Found during Task 9 code review — keep the repository
    // read inside the try.
    ref.read(chatIsSendingProvider.notifier).state = true;
    try {
      final repository = ref.read(chatRepositoryProvider);
      final reply = await repository.send(text: trimmed, history: history);
      state = AsyncData([...withUser, reply]);
    } catch (_) {
      state = AsyncData([...withUser, _errorMessage()]);
    } finally {
      ref.read(chatIsSendingProvider.notifier).state = false;
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
