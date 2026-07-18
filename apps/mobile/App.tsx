import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import {
  FlatList,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import type { Item } from "@abridge/shared";
import { api } from "./src/api";

export default function App() {
  const [health, setHealth] = useState("checking…");
  const [items, setItems] = useState<Item[]>([]);
  const [title, setTitle] = useState("");

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("api unreachable"));
    api.listItems().then(setItems).catch(() => {});
  }, []);

  async function addItem() {
    if (!title.trim()) return;
    const item = await api.createItem({ title: title.trim() });
    setItems((prev) => [...prev, item]);
    setTitle("");
  }

  return (
    <View style={styles.container}>
      <Text style={styles.h1}>Abridge — Mobile</Text>
      <Text style={styles.status}>API status: {health}</Text>

      <View style={styles.row}>
        <TextInput
          style={styles.input}
          placeholder="New item title"
          value={title}
          onChangeText={setTitle}
          onSubmitEditing={addItem}
        />
        <TouchableOpacity style={styles.button} onPress={addItem}>
          <Text style={styles.buttonText}>Add</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        style={styles.list}
        data={items}
        keyExtractor={(it) => it.id}
        renderItem={({ item }) => <Text style={styles.item}>{item.title}</Text>}
      />
      <StatusBar style="auto" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#fff", paddingTop: 80, paddingHorizontal: 20 },
  h1: { fontSize: 24, fontWeight: "700", marginBottom: 4 },
  status: { color: "#555", marginBottom: 16 },
  row: { flexDirection: "row", gap: 8, marginBottom: 16 },
  input: { flex: 1, borderWidth: 1, borderColor: "#ccc", borderRadius: 8, padding: 10 },
  button: { backgroundColor: "#111", borderRadius: 8, paddingHorizontal: 16, justifyContent: "center" },
  buttonText: { color: "#fff", fontWeight: "600" },
  list: { flex: 1 },
  item: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: "#eee" },
});
