import { useEffect, useState } from "react";
import type { Item } from "@abridge/shared";
import { api } from "./api";

export default function App() {
  const [health, setHealth] = useState<string>("checking…");
  const [items, setItems] = useState<Item[]>([]);
  const [title, setTitle] = useState("");

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("api unreachable"));
    api.listItems().then(setItems).catch(() => {});
  }, []);

  async function addItem(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    const item = await api.createItem({ title: title.trim() });
    setItems((prev) => [...prev, item]);
    setTitle("");
  }

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 480, margin: "3rem auto", padding: "0 1rem" }}>
      <h1>Abridge — Web</h1>
      <p>
        API status: <strong>{health}</strong>
      </p>

      <form onSubmit={addItem} style={{ display: "flex", gap: 8 }}>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="New item title"
          style={{ flex: 1, padding: 8 }}
        />
        <button type="submit">Add</button>
      </form>

      <ul>
        {items.map((it) => (
          <li key={it.id}>{it.title}</li>
        ))}
      </ul>
    </main>
  );
}
