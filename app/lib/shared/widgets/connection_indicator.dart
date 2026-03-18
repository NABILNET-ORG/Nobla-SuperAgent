import 'package:flutter/material.dart';

class ConnectionIndicator extends StatelessWidget {
  final bool isConnected;
  const ConnectionIndicator({super.key, this.isConnected = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        color: isConnected ? Colors.green : Colors.grey,
        shape: BoxShape.circle,
      ),
    );
  }
}
