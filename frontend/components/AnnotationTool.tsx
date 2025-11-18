"use client";

import { useState, useEffect, useCallback } from "react";
import styles from "./AnnotationTool.module.css";

interface Thumbnail {
  filename: string;
  date_display: string;
  thumbnail_data_url?: string;
  original_path: string;
}

interface FarmData {
  farm_id: string;
  image_count: number;
  thumbnails: Thumbnail[];
  current_index?: number;
  total_farms?: number;
}

interface StatusData {
  current_farm_id: string;
  current_farm_index: number;
  total_farms: number;
  completed: boolean;
}

export function AnnotationTool() {
  const [currentFarm, setCurrentFarm] = useState<string>("");
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [totalFarms, setTotalFarms] = useState<number>(0);
  const [selectedImageIndex, setSelectedImageIndex] = useState<number | null>(
    null
  );
  const [currentFarmData, setCurrentFarmData] = useState<FarmData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [message, setMessage] = useState<{
    text: string;
    type: "success" | "error" | "info";
  } | null>(null);
  const [completed, setCompleted] = useState<boolean>(false);

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5005";

  const showMessage = useCallback(
    (text: string, type: "success" | "error" | "info" = "info") => {
      setMessage({ text, type });
      setTimeout(() => setMessage(null), 4000);
    },
    []
  );

  const loadFarmData = useCallback(
    async (farmId: string) => {
      setLoading(true);
      setSelectedImageIndex(null);

      try {
        const response = await fetch(`${API_BASE}/api/farm/${farmId}`);
        const data: FarmData & { selected_index?: number } =
          await response.json();

        if (!response.ok) {
          throw new Error("Failed to load farm data");
        }

        setCurrentFarmData(data);
        setCurrentFarm(data.farm_id || farmId);
        if (
          typeof data.selected_index === "number" &&
          data.selected_index >= 0
        ) {
          setSelectedImageIndex(data.selected_index);
        }
        if (typeof data.current_index === "number") {
          setCurrentIndex(data.current_index);
        }
        if (typeof data.total_farms === "number") {
          setTotalFarms(data.total_farms);
        }
      } catch (error) {
        console.error("Error loading farm data:", error);
        showMessage("Error loading farm data", "error");
      } finally {
        setLoading(false);
      }
    },
    [API_BASE, showMessage]
  );

  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/status`);
        const data: StatusData = await response.json();

        setCurrentIndex(data.current_farm_index);
        setCurrentFarm(data.current_farm_id);
        setTotalFarms(data.total_farms);

        if (data.completed) {
          setCompleted(true);
          return;
        }

        await loadFarmData(data.current_farm_id);
      } catch (error) {
        console.error("Error loading initial data:", error);
        showMessage("Error loading application data", "error");
      }
    };

    loadInitialData();
  }, [API_BASE, loadFarmData, showMessage]);

  const navigateFarm = async (direction: "prev" | "next") => {
    try {
      const response = await fetch(`${API_BASE}/api/navigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include", // Ensure cookies/session are sent
        body: JSON.stringify({ direction }),
      });

      const data = await response.json();
      if (typeof data.current_index === "number") {
        setCurrentIndex(data.current_index);
      }
      if (typeof data.total_farms === "number") {
        setTotalFarms(data.total_farms);
      }
      await loadFarmData(data.current_farm);
    } catch (error) {
      console.error("Error navigating:", error);
      showMessage("Error navigating between farms", "error");
    }
  };

  const saveAnnotation = async () => {
    if (selectedImageIndex === null || !currentFarmData) {
      showMessage("Please select an image before saving", "error");
      return;
    }

    const selectedThumbnail = currentFarmData.thumbnails[selectedImageIndex];

    try {
      const response = await fetch(`${API_BASE}/api/save_annotation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          farm_id: currentFarmData.farm_id,
          selected_image: selectedThumbnail.filename,
          image_path: selectedThumbnail.original_path,
          total_images: currentFarmData.image_count,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        showMessage(data.message, "success");

        if (currentIndex < totalFarms - 1) {
          setTimeout(() => navigateFarm("next"), 1500);
        } else {
          setTimeout(() => setCompleted(true), 1500);
        }
      } else {
        throw new Error(data.error || "Failed to save annotation");
      }
    } catch (error) {
      console.error("Error saving annotation:", error);
      showMessage("Error saving annotation", "error");
    }
  };

  const skipFarm = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/skip_farm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include", // Ensure cookies/session are sent
        body: JSON.stringify({ farm_index: currentIndex }),
      });

      const data = await response.json();

      if (response.ok) {
        showMessage(data.message, "info");

        if (typeof data.current_index === "number") {
          setCurrentIndex(data.current_index);
        }
        if (typeof data.total_farms === "number") {
          setTotalFarms(data.total_farms);
        }

        if (data.completed) {
          setTimeout(() => setCompleted(true), 1500);
        } else {
          setTimeout(() => loadFarmData(data.current_farm_id), 1500);
        }
      } else {
        throw new Error(data.error || "Failed to skip farm");
      }
    } catch (error) {
      console.error("Error skipping farm:", error);
      showMessage("Error skipping farm", "error");
    }
  };

  useEffect(() => {
    const handleKeyboard = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      switch (e.key) {
        case "ArrowLeft":
          if (currentIndex > 0) navigateFarm("prev");
          break;
        case "ArrowRight":
          if (currentIndex < totalFarms - 1) navigateFarm("next");
          break;
        case "Enter":
          if (selectedImageIndex !== null) saveAnnotation();
          break;
      }
    };

    document.addEventListener("keydown", handleKeyboard);
    return () => document.removeEventListener("keydown", handleKeyboard);
  }, [currentIndex, totalFarms, selectedImageIndex]);

  if (completed) {
    return (
      <div className={styles.container}>
        <header className={styles.header}>
          <h1>🌾 Farm Harvest Annotation Tool</h1>
          <div className={styles.status}>Session completed</div>
        </header>
        <main className={styles.mainContent}>
          <div className={styles.farmInfo}>
            <h2>Annotation Complete! 🎉</h2>
            <p>All farms have been processed.</p>
          </div>
        </main>
        {/* No reset session button */}
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1>🌾 Farm Harvest Annotation Tool</h1>
        <div className={styles.status}>
          Farm {currentIndex + 1} of {totalFarms}
        </div>
      </header>

      <nav className={styles.navigation}>
        <button
          onClick={() => navigateFarm("prev")}
          className={styles.navBtn}
          disabled={currentIndex <= 0}
        >
          ← Previous Farm
        </button>
        <div className={styles.progressContainer}>
          <div className={styles.progress}>
            {currentIndex + 1} / {totalFarms}
          </div>
        </div>
        <button
          onClick={() => navigateFarm("next")}
          className={styles.navBtn}
          disabled={
            currentIndex >= totalFarms - 1 || selectedImageIndex === null
          }
        >
          Next Farm →
        </button>
      </nav>

      <main className={styles.mainContent}>
        <div className={styles.farmInfo}>
          <h2>Farm ID: {currentFarmData?.farm_id}</h2>
          <p>{currentFarmData?.image_count} images available</p>
        </div>

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner}></div>
            <p>Loading farm images...</p>
          </div>
        ) : currentFarmData?.thumbnails?.length ? (
          <div className={styles.imagesContainer}>
            <div className={styles.imagesHeader}>
              <h3>📅 Temporal Image Timeline</h3>
              <p>
                Select harvest-ready images from the 12-month timeline below
              </p>
            </div>
            <div className={styles.imagesGrid}>
              {currentFarmData.thumbnails.map((thumbnail, index) => {
                const farmId = encodeURIComponent(currentFarmData.farm_id);
                const filename = encodeURIComponent(thumbnail.filename);
                const src =
                  thumbnail.thumbnail_data_url ||
                  `${API_BASE}/api/thumbnail?farm_id=${farmId}&filename=${filename}&w=300&h=300`;

                return (
                  <div
                    key={index}
                    className={`${styles.imageItem} ${
                      selectedImageIndex === index ? styles.selected : ""
                    }`}
                    onClick={() => setSelectedImageIndex(index)}
                  >
                    <img
                      src={src}
                      alt={thumbnail.filename}
                      loading="lazy"
                      onError={(e) => {
                        console.error(
                          `Failed to load image: ${thumbnail.filename}`
                        );
                        // Set a placeholder or keep the broken image icon
                        e.currentTarget.src =
                          "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjMwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMzAwIiBoZWlnaHQ9IjMwMCIgZmlsbD0iI2NjYyIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjE0IiBmaWxsPSIjMDAwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+SW1hZ2UgRmFpbGVkPC90ZXh0Pjwvc3ZnPg==";
                      }}
                    />
                    <div className={styles.imageDate}>
                      {thumbnail.date_display}
                    </div>
                    <div className={styles.imageFilename}>
                      {thumbnail.filename}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className={styles.noImages}>
            <p>No images found for this farm.</p>
          </div>
        )}
      </main>

      <footer className={styles.actions}>
        <button
          onClick={saveAnnotation}
          className={`${styles.actionBtn} ${styles.primary}`}
          disabled={selectedImageIndex === null}
        >
          Save Selection
        </button>
        <button
          onClick={skipFarm}
          className={`${styles.actionBtn} ${styles.secondary}`}
        >
          Skip Farm
        </button>
        {/* No reset session button */}
      </footer>

      {message && (
        <div className={`${styles.message} ${styles[message.type]}`}>
          {message.text}
        </div>
      )}
    </div>
  );
}
