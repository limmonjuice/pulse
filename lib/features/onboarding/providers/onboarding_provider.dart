import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Whether the disclaimer has been accepted this session. In-memory only —
/// resets on app restart, which is fine for now (no persistence package).
class DisclaimerNotifier extends Notifier<bool> {
  @override
  bool build() => false;

  void accept() => state = true;
}

final disclaimerAcceptedProvider = NotifierProvider<DisclaimerNotifier, bool>(
  DisclaimerNotifier.new,
);
