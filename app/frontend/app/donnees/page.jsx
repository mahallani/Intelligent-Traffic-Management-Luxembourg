"use client";
// 2026-11-03: this page moved to /technique/ (previous version: donnees/page.jsx.bak_20261103). Kept so that old links still work.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function Moved() {
  const router = useRouter();
  useEffect(() => { router.replace("/technique/"); }, [router]);
  return <p className="muted">Cette page a été déplacée : <Link href="/technique/">Section technique</Link>.</p>;
}
