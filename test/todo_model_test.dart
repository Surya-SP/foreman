import 'package:flutter_test/flutter_test.dart';
import 'package:prove_app/models/todo.dart';

void main() {
  test('Todo json round-trip', () {
    final t = Todo(id: '1', title: 'a', done: true);
    final t2 = Todo.fromJson(t.toJson());
    expect(t2.id, '1');
    expect(t2.title, 'a');
    expect(t2.done, isTrue);
  });
}
