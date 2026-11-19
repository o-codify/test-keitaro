import { useEffect, useRef, useState } from "react";
import { api, Offer } from "../api";

type Props = {
  value: Offer | null;
  onChange: (offer: Offer | null) => void;
  placeholder?: string;
  excludeIds?: number[];
};

/** Поиск офферов по названию или ID: ходит на /api/offers (кэш офферов Keitaro). */
export default function OfferAutocomplete({ value, onChange, placeholder, excludeIds = [] }: Props) {
  const [query, setQuery] = useState(value ? label(value) : "");
  const [items, setItems] = useState<Offer[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);
  const requestId = useRef(0);

  useEffect(() => {
    setQuery(value ? label(value) : "");
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const id = ++requestId.current;
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .offers(value && query === label(value) ? "" : query)
        .then((res) => {
          if (id !== requestId.current) return;
          setItems(res.filter((o) => !excludeIds.includes(o.id)));
          setHighlight(0);
          setError("");
        })
        .catch((e) => id === requestId.current && setError(e.message))
        .finally(() => id === requestId.current && setLoading(false));
    }, 200);
    return () => clearTimeout(timer);
    // excludeIds сравниваем по содержимому
  }, [query, open, excludeIds.join(",")]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const select = (offer: Offer) => {
    onChange(offer);
    setQuery(label(offer));
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter")) {
      setOpen(true);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (items[highlight]) select(items[highlight]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="autocomplete" ref={boxRef}>
      <input
        value={query}
        placeholder={placeholder ?? "Поиск оффера по названию или ID"}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onKeyDown={onKeyDown}
      />
      {open && (
        <ul className="autocomplete-list">
          {loading && items.length === 0 && <li className="muted">Поиск…</li>}
          {error && <li className="error-text">{error}</li>}
          {!loading && !error && items.length === 0 && <li className="muted">Ничего не найдено</li>}
          {items.map((offer, i) => (
            <li
              key={offer.id}
              className={i === highlight ? "highlight" : ""}
              onMouseEnter={() => setHighlight(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                select(offer);
              }}
            >
              <span className="offer-id">#{offer.id}</span> {offer.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function label(offer: Offer) {
  return `#${offer.id} ${offer.name}`;
}
