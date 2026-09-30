const multer = require('multer');
const path = require('path');
const fs = require('fs');
const os = require('os');

const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        if(!req._tmpdir) req._tmpdir = fs.mkdtempSync(path.join(os.tmpdir(), 'capex-'));
        cb(null, req._tmpdir);
    },
    filename: (req, file, cb) => {
        const ext = path.extname(file.originalname || '');
        const base = path.basename(file.originalname || 'file', ext);
        cb(null, `${base}-${Date.now()}${ext}`);
    }
});

const upload = multer({ storage, limits: { fileSize: 200 * 1024 * 1024 } });

module.exports = { storage, upload }