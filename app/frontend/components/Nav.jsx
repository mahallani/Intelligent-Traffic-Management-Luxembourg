"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "Pilotage"],
  ["/resultats/", "Résultats et comparaison"],
  ["/donnees/", "Données"],
  ["/rapports/", "Rapports"],
  ["/xai/", "Explicabilité XAI"],
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="topbar">
      <span className="brand">Intelligent Traffic Management Luxembourg</span>
      <nav aria-label="Navigation principale">
        {LINKS.map(([href, label]) => (
          <Link key={href} href={href} aria-current={path === href || path + "/" === href ? "page" : undefined}>
            {label}
          </Link>
        ))}
      </nav>
      <span className="origin">Kirchberg · 4 carrefours · Simulation SUMO (LuST, vers 2015) – données simulées, aucune mesure réelle</span>
    </header>
  );
}
