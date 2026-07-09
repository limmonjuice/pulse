import 'package:firebase_auth/firebase_auth.dart';

/// Turns an error thrown by [AuthRepository] into a warm, plain-language
/// message. Never surface a raw Firebase error code or exception string
/// to the user.
String authErrorMessage(Object error) {
  if (error is FirebaseAuthException) {
    switch (error.code) {
      case 'wrong-password':
      case 'invalid-credential':
        return "That password doesn't look right — want to try again?";
      case 'email-already-in-use':
        return "Looks like that email already has an account — try logging in instead.";
      case 'weak-password':
        return "That password's a little too simple — try adding a few more characters.";
      case 'invalid-email':
        return "That email address doesn't look quite right — mind double-checking it?";
      case 'user-not-found':
        return "We couldn't find an account with that email — want to sign up instead?";
      case 'network-request-failed':
        return "We're having trouble connecting — check your internet and try again.";
      default:
        return "Something went wrong on our end — please try again in a moment.";
    }
  }
  return "Something went wrong on our end — please try again in a moment.";
}
