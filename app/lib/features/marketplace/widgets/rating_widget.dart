import 'package:flutter/material.dart';

class RatingWidget extends StatelessWidget {
  final double currentRating;
  final ValueChanged<int>? onRate;

  const RatingWidget({
    super.key,
    required this.currentRating,
    this.onRate,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(5, (index) {
        final starValue = index + 1;
        final filled = starValue <= currentRating.round();
        return GestureDetector(
          onTap: onRate != null ? () => onRate!(starValue) : null,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 2),
            child: Icon(
              filled ? Icons.star : Icons.star_border,
              color: Colors.amber.shade700,
              size: 24,
            ),
          ),
        );
      }),
    );
  }
}
