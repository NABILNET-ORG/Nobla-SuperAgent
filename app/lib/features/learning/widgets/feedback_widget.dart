import 'package:flutter/material.dart';

class FeedbackWidget extends StatefulWidget {
  final String messageId;
  final ValueChanged<int> onFeedback;

  const FeedbackWidget({
    super.key,
    required this.messageId,
    required this.onFeedback,
  });

  @override
  State<FeedbackWidget> createState() => _FeedbackWidgetState();
}

class _FeedbackWidgetState extends State<FeedbackWidget> {
  int _rating = 0;
  bool _expanded = false;

  void _rate(int value) {
    setState(() {
      _rating = value;
      _expanded = true;
    });
    widget.onFeedback(value);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: Icon(
                _rating == 1 ? Icons.thumb_up : Icons.thumb_up_outlined,
                size: 18,
              ),
              onPressed: () => _rate(1),
            ),
            IconButton(
              icon: Icon(
                _rating == -1 ? Icons.thumb_down : Icons.thumb_down_outlined,
                size: 18,
              ),
              onPressed: () => _rate(-1),
            ),
          ],
        ),
        if (_expanded)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(5, (i) => Icon(
                Icons.star_border,
                size: 20,
                color: Theme.of(context).colorScheme.primary,
              )),
            ),
          ),
      ],
    );
  }
}
