const request = require('supertest');
const { createApp } = require('../src/app');

let app;

beforeEach(() => {
  app = createApp(':memory:');
});

afterEach(() => {
  if (app._db) app._db.close();
});

// Helper
const validTask = { title: 'Test task', description: 'A description', priority: 'medium' };

describe('POST /api/tasks', () => {
  test('1: creates a task with valid data', async () => {
    const res = await request(app).post('/api/tasks').send(validTask);
    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({
      id: 1,
      title: 'Test task',
      description: 'A description',
      priority: 'medium',
    });
    expect(res.body.created_at).toBeDefined();
    expect(res.body.updated_at).toBeDefined();
  });

  test('2: creates a task without description (defaults to empty string)', async () => {
    const res = await request(app).post('/api/tasks').send({ title: 'No desc', priority: 'low' });
    expect(res.status).toBe(201);
    expect(res.body.description).toBe('');
  });

  test('3: rejects empty body', async () => {
    const res = await request(app).post('/api/tasks').send({});
    expect(res.status).toBe(422);
    expect(res.body.errors.length).toBeGreaterThanOrEqual(2);
  });

  test('4: rejects missing title', async () => {
    const res = await request(app).post('/api/tasks').send({ priority: 'high' });
    expect(res.status).toBe(422);
    expect(res.body.errors[0]).toMatch(/title/i);
  });

  test('5: rejects empty string title', async () => {
    const res = await request(app).post('/api/tasks').send({ title: '', priority: 'high' });
    expect(res.status).toBe(422);
  });

  test('6: rejects whitespace-only title', async () => {
    const res = await request(app).post('/api/tasks').send({ title: '   ', priority: 'high' });
    expect(res.status).toBe(422);
  });

  test('7: rejects missing priority', async () => {
    const res = await request(app).post('/api/tasks').send({ title: 'Test' });
    expect(res.status).toBe(422);
    expect(res.body.errors.some(e => /priority/i.test(e))).toBe(true);
  });

  test('8: rejects invalid priority', async () => {
    const res = await request(app).post('/api/tasks').send({ title: 'Test', priority: 'urgent' });
    expect(res.status).toBe(422);
  });

  test('9: rejects numeric title', async () => {
    const res = await request(app).post('/api/tasks').send({ title: 123, priority: 'low' });
    expect(res.status).toBe(422);
  });

  test('10: trims title whitespace', async () => {
    const res = await request(app).post('/api/tasks').send({ title: '  Trimmed  ', priority: 'low' });
    expect(res.status).toBe(201);
    expect(res.body.title).toBe('Trimmed');
  });
});

describe('GET /api/tasks', () => {
  test('11: returns empty array when no tasks', async () => {
    const res = await request(app).get('/api/tasks');
    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  test('12: returns all created tasks in order', async () => {
    await request(app).post('/api/tasks').send({ title: 'First', priority: 'low' });
    await request(app).post('/api/tasks').send({ title: 'Second', priority: 'high' });

    const res = await request(app).get('/api/tasks');
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(2);
    expect(res.body[0].title).toBe('First');
    expect(res.body[1].title).toBe('Second');
  });
});

describe('PUT /api/tasks/:id', () => {
  test('13: updates title only', async () => {
    await request(app).post('/api/tasks').send(validTask);
    const res = await request(app).put('/api/tasks/1').send({ title: 'Updated' });
    expect(res.status).toBe(200);
    expect(res.body.title).toBe('Updated');
    expect(res.body.priority).toBe('medium'); // unchanged
  });

  test('14: updates priority only', async () => {
    await request(app).post('/api/tasks').send(validTask);
    const res = await request(app).put('/api/tasks/1').send({ priority: 'critical' });
    expect(res.status).toBe(200);
    expect(res.body.priority).toBe('critical');
    expect(res.body.title).toBe('Test task'); // unchanged
  });

  test('15: returns 404 for nonexistent task', async () => {
    const res = await request(app).put('/api/tasks/999').send({ title: 'Nope' });
    expect(res.status).toBe(404);
  });

  test('16: returns 422 for invalid priority on update', async () => {
    await request(app).post('/api/tasks').send(validTask);
    const res = await request(app).put('/api/tasks/1').send({ priority: 'extreme' });
    expect(res.status).toBe(422);
  });

  test('17: returns 422 for empty title on update', async () => {
    await request(app).post('/api/tasks').send(validTask);
    const res = await request(app).put('/api/tasks/1').send({ title: '' });
    expect(res.status).toBe(422);
  });

  test('18: returns 400 for non-numeric id', async () => {
    const res = await request(app).put('/api/tasks/abc').send({ title: 'Nope' });
    expect(res.status).toBe(400);
  });

  test('19: updates description to empty string', async () => {
    await request(app).post('/api/tasks').send(validTask);
    const res = await request(app).put('/api/tasks/1').send({ description: '' });
    expect(res.status).toBe(200);
    expect(res.body.description).toBe('');
  });
});

describe('DELETE /api/tasks/:id', () => {
  test('20: deletes existing task', async () => {
    await request(app).post('/api/tasks').send(validTask);
    const res = await request(app).delete('/api/tasks/1');
    expect(res.status).toBe(204);

    const list = await request(app).get('/api/tasks');
    expect(list.body).toHaveLength(0);
  });

  test('21: returns 404 for nonexistent task', async () => {
    const res = await request(app).delete('/api/tasks/999');
    expect(res.status).toBe(404);
  });

  test('22: returns 400 for non-numeric id', async () => {
    const res = await request(app).delete('/api/tasks/abc');
    expect(res.status).toBe(400);
  });

  test('23: double delete returns 404', async () => {
    await request(app).post('/api/tasks').send(validTask);
    await request(app).delete('/api/tasks/1');
    const res = await request(app).delete('/api/tasks/1');
    expect(res.status).toBe(404);
  });
});

describe('GET /api/tasks/stats', () => {
  test('24: returns all zeros when empty', async () => {
    const res = await request(app).get('/api/tasks/stats');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ low: 0, medium: 0, high: 0, critical: 0, total: 0 });
  });

  test('25: counts tasks by priority', async () => {
    await request(app).post('/api/tasks').send({ title: 'A', priority: 'low' });
    await request(app).post('/api/tasks').send({ title: 'B', priority: 'low' });
    await request(app).post('/api/tasks').send({ title: 'C', priority: 'high' });
    await request(app).post('/api/tasks').send({ title: 'D', priority: 'critical' });

    const res = await request(app).get('/api/tasks/stats');
    expect(res.body).toEqual({ low: 2, medium: 0, high: 1, critical: 1, total: 4 });
  });

  test('26: stats update after delete', async () => {
    await request(app).post('/api/tasks').send({ title: 'A', priority: 'low' });
    await request(app).post('/api/tasks').send({ title: 'B', priority: 'low' });
    await request(app).delete('/api/tasks/1');

    const res = await request(app).get('/api/tasks/stats');
    expect(res.body.low).toBe(1);
    expect(res.body.total).toBe(1);
  });
});

describe('Concurrent requests', () => {
  test('27: handles multiple concurrent creates', async () => {
    const promises = Array.from({ length: 10 }, (_, i) =>
      request(app).post('/api/tasks').send({ title: `Task ${i}`, priority: 'medium' })
    );
    const results = await Promise.all(promises);

    results.forEach(r => expect(r.status).toBe(201));

    const ids = new Set(results.map(r => r.body.id));
    expect(ids.size).toBe(10); // all unique IDs

    const list = await request(app).get('/api/tasks');
    expect(list.body).toHaveLength(10);
  });

  test('28: concurrent create and read', async () => {
    // Seed a task first
    await request(app).post('/api/tasks').send({ title: 'Seed', priority: 'low' });

    const promises = [
      request(app).post('/api/tasks').send({ title: 'New', priority: 'high' }),
      request(app).get('/api/tasks'),
      request(app).get('/api/tasks/stats'),
    ];
    const [create, list, stats] = await Promise.all(promises);

    expect(create.status).toBe(201);
    expect(list.status).toBe(200);
    expect(stats.status).toBe(200);
  });
});

describe('Edge cases', () => {
  test('29: returns 404 for unknown routes', async () => {
    const res = await request(app).get('/api/nonexistent');
    expect(res.status).toBe(404);
  });

  test('30: PUT with no body fields still returns the task unchanged', async () => {
    await request(app).post('/api/tasks').send(validTask);
    const res = await request(app).put('/api/tasks/1').send({});
    expect(res.status).toBe(200);
    expect(res.body.title).toBe('Test task');
  });

  test('31: negative id returns 400', async () => {
    const res = await request(app).put('/api/tasks/-1').send({ title: 'Nope' });
    expect(res.status).toBe(400);
  });

  test('32: zero id returns 400', async () => {
    const res = await request(app).delete('/api/tasks/0');
    expect(res.status).toBe(400);
  });

  test('33: very long title is accepted', async () => {
    const longTitle = 'A'.repeat(10000);
    const res = await request(app).post('/api/tasks').send({ title: longTitle, priority: 'low' });
    expect(res.status).toBe(201);
    expect(res.body.title).toBe(longTitle);
  });

  test('34: all four priority values accepted', async () => {
    for (const p of ['low', 'medium', 'high', 'critical']) {
      const res = await request(app).post('/api/tasks').send({ title: `Task ${p}`, priority: p });
      expect(res.status).toBe(201);
    }
  });

  test('35: case-sensitive priority rejection', async () => {
    const res = await request(app).post('/api/tasks').send({ title: 'Test', priority: 'High' });
    expect(res.status).toBe(422);
  });
});
