# Farm Harvest Annotation Tool

A modern web-based tool for annotating farm harvest images with temporal image selection. This project features a Next.js frontend and a FastAPI backend, supporting large-scale annotation workflows with advanced features and performance optimizations.

---

## 🚀 Quick Start

### Automated Setup (Recommended)

**Windows (PowerShell):**

```powershell
.\setup.ps1
```

**Linux/Mac:**

```bash
chmod +x setup.sh
./setup.sh
```

### Manual Setup

#### 1. Backend Setup

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 5005 --reload
```

Backend runs on `http://localhost:5005`

#### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000`

---

## 📁 Project Structure

```
CNH/
├── app/                    # Flask/FastAPI backend
│   ├── app.py             # Main Flask application (with CORS enabled)
│   ├── app_fastapi.py     # FastAPI version (see FASTAPI_MIGRATION.md)
│   ├── static/            # Static files (thumbnails, CSS, JS)
│   ├── templates/         # (Legacy) Flask templates
│   ├── requirements.txt   # Python dependencies (Flask)
│   ├── requirements_fastapi.txt # Python dependencies (FastAPI)
│   └── ...
├── frontend/              # Next.js frontend
│   ├── app/              # Next.js app directory
│   ├── components/       # React components
│   ├── public/           # Static assets
│   ├── .env.local        # Environment variables
│   └── package.json      # Node dependencies
├── farm_dataset/         # Farm images dataset
├── thumbnail_cache/      # Generated thumbnails
├── harvest_annotations.csv # Annotation output
├── farm_index.json       # Farm index for large datasets
└── ...
```

---

## ✨ Features

- **Image Annotation**: Select harvest-ready images from a temporal timeline
- **Navigation**: Browse through farms with keyboard shortcuts or buttons
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Real-time Updates**: Instant feedback on save/skip actions
- **Preloading**: Optimized image loading for smooth navigation
- **Session Management**: Save progress and reset as needed
- **Batch Claiming**: Annotators can claim batches of farms for efficient workflow
- **Thumbnail Caching**: Disk-backed LRU cache for fast image loading
- **Admin Diagnostics**: Inspect task assignments and progress

---

## 🎮 Usage

1. **View Farm Images**: Images are displayed in a grid showing the 12-month timeline
2. **Select Image**: Click on an image to mark it as harvest-ready
3. **Save**: Click "Save Selection" or press `Enter` to record your annotation
4. **Navigate**: Use Previous/Next buttons or arrow keys
5. **Skip**: Skip farms without selection if needed

---

## ⌨️ Keyboard Shortcuts

- `←` Arrow Left: Previous Farm
- `→` Arrow Right: Next Farm
- `Enter`: Save Selection

---

## 🔧 Configuration

### Backend (Flask/FastAPI)

- Edit `app/app.py` or `app/app_fastapi.py` for:
  - Dataset directory path
  - Port configuration
  - CORS settings
- See `BACKEND_SETUP.md` for CORS and production setup

### Frontend (Next.js)

- Edit `frontend/.env.local` for API URL and environment variables
- Next.js rewrites are configured to proxy API requests to the backend

---

## 🌐 API Endpoints

- `GET /api/status` - Get current session status
- `GET /api/farm/:id` - Get farm data and images
- `POST /api/navigate` - Navigate between farms
- `POST /api/save_annotation` - Save annotation
- `POST /api/skip_farm` - Skip current farm
- `GET /api/reset` - Reset session
- `GET /api/thumbnail` - Get thumbnail image
- `POST /api/login` - Login annotator
- `POST /api/claim_batch` - Claim batch of farms
- `POST /api/release_batch` - Release batch
- `GET /api/admin/tasks` - Admin diagnostics

---

## 💾 Output

Annotations are saved to `harvest_annotations.csv` with the following structure:

```csv
farm_id,selected_image,image_path,total_images,timestamp
34011571310001,Oct_2024.tif,/path/to/image.tif,6,2025-09-30T14:30:00
```

---

## 📦 Technologies

### Backend

- Flask 2.0+ or FastAPI 0.104+
- Flask-CORS 3.0+ or FastAPI CORS Middleware
- Pillow (image processing)
- Python 3.8+
- SQLite (default) or PostgreSQL (scalable)

### Frontend

- Next.js 16
- React 19
- TypeScript 5
- CSS Modules

---

## 🛠️ Advanced Features & Notes

- **Farm Index**: For large datasets, `farm_index.json` is used to avoid repeated filesystem scans.
- **Batch Claiming**: Annotators can claim/release batches of farms for efficient annotation.
- **Thumbnail Cache**: Disk-backed LRU cache in `thumbnail_cache/` for fast image serving.
- **Admin Diagnostics**: `/api/admin/tasks` for monitoring assignments and progress.
- **Session State**: Managed by the backend; per-annotator CSV backups in `annotations_by_user/<annotator>/`.
- **Production**: Use gunicorn (Flask) or uvicorn (FastAPI) with a reverse proxy (nginx) and HTTPS.
- **CORS**: See `BACKEND_SETUP.md` for enabling CORS for frontend-backend communication.
- **Frontend**: All Flask templates have been converted to React components with TypeScript and CSS Modules.

---

## 🐛 Troubleshooting

### CORS Errors

- Ensure Flask-CORS is installed: `pip install flask-cors`
- Check Flask/FastAPI app is running on the correct port
- Verify Next.js config has correct API URL

### Images Not Loading

- Check `farm_dataset` directory exists
- Verify image paths in dataset
- Clear thumbnail cache if needed

### Port Already in Use

- Backend: Change port in `app.py` or `app_fastapi.py`
- Frontend: Run with `npm run dev -- -p 3001`
