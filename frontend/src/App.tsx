import { BrowserRouter, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import SyllabusPage from "./pages/SyllabusPage";
import GenerationPage from "./pages/GenerationPage";
import DecksListPage from "./pages/DecksListPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/decks" element={<DecksListPage />} />
        <Route path="/decks/:deckId/syllabus" element={<SyllabusPage />} />
        <Route path="/decks/:deckId/generate" element={<GenerationPage />} />
      </Routes>
    </BrowserRouter>
  );
}
