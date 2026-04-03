const path = require('path');
const { createApp } = require('./app');

const PORT = process.env.PORT || 3000;
const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', 'data', 'tasks.db');

// Ensure data dir exists
const fs = require('fs');
fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });

const app = createApp(DB_PATH);

app.listen(PORT, () => {
  console.log(`Task API running on port ${PORT}`);
});
