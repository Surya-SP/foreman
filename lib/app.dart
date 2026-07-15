import 'package:flutter/material.dart';

class ProveApp extends StatelessWidget {
  const ProveApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Todos',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2196F3)),
        useMaterial3: true,
      ),
      home: const Scaffold(body: Center(child: Text('Todos'))),
    );
  }
}
