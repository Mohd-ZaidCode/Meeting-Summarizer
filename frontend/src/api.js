const API_BASE = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data.detail || data.message || `Request failed (${response.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  listMeetings: () => request("/api/meetings"),
  getMeeting: (id) => request(`/api/meetings/${id}`),
  uploadMeeting: async (file, onProgress) => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/meetings`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      };
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText || "{}");
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else reject(new Error(data.detail || "Upload failed"));
        } catch {
          reject(new Error("Upload failed"));
        }
      };
      xhr.onerror = () => reject(new Error("Network error while uploading"));
      const form = new FormData();
      form.append("file", file);
      xhr.send(form);
    });
  },
  toggleAction: (meetingId, actionId, done) =>
    request(`/api/meetings/${meetingId}/actions/${actionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ done }),
    }),
  deleteMeeting: (id) => request(`/api/meetings/${id}`, { method: "DELETE" }),
  audioUrl: (id) => `${API_BASE}/api/meetings/${id}/audio`,
  saveOpenAIKey: (api_key) =>
    request("/api/settings/openai-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key }),
    }),
  clearOpenAIKey: () => request("/api/settings/openai-key", { method: "DELETE" }),
};
