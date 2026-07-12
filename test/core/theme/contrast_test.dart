// test/core/theme/contrast_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_app/core/theme/contrast.dart';

void main() {
  test('relativeLuminance of pure black is 0, pure white is 1', () {
    expect(relativeLuminance(Colors.black), closeTo(0.0, 0.0001));
    expect(relativeLuminance(Colors.white), closeTo(1.0, 0.0001));
  });

  test('contrastRatio of black on white is the maximum, 21:1', () {
    expect(contrastRatio(Colors.black, Colors.white), closeTo(21.0, 0.01));
  });

  test('contrastRatio of a color against itself is the minimum, 1:1', () {
    expect(contrastRatio(Colors.white, Colors.white), closeTo(1.0, 0.0001));
    expect(
      contrastRatio(const Color(0xFF6FA8B5), const Color(0xFF6FA8B5)),
      closeTo(1.0, 0.0001),
    );
  });

  test('contrastRatio is symmetric — argument order does not matter', () {
    const a = Color(0xFF33403F);
    const b = Color(0xFF6FA8B5);
    expect(contrastRatio(a, b), contrastRatio(b, a));
  });

  test(
    // Known reference pair (WCAG examples commonly cite #767676 on
    // white as landing almost exactly on the 4.5:1 AA line) — confirms
    // this implementation matches the standard formula, not just an
    // internally-consistent one.
    '#767676 on white is ~4.5:1, the textbook AA boundary example',
    () {
      expect(
        contrastRatio(const Color(0xFF767676), Colors.white),
        closeTo(4.54, 0.02),
      );
    },
  );
}
