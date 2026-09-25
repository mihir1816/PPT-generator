import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import HomePage from "./pages/HomePage";
import SyllabusPage from "./pages/SyllabusPage";
import GenerationPage from "./pages/GenerationPage";
import DecksListPage from "./pages/DecksListPage";

function NavBar() {
  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link to="/" className="text-lg font-bold text-gray-900">
          TCG
        </Link>
        <div className="flex gap-4">
          <Link
            to="/"
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            New
          </Link>
          <Link
            to="/decks"
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            My Decks
          </Link>
        </div>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <NavBar />
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/decks" element={<DecksListPage />} />
          <Route path="/decks/:deckId/syllabus" element={<SyllabusPage />} />
          <Route path="/decks/:deckId/generate" element={<GenerationPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
