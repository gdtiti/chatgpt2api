"use client";

import { useEffect, useMemo, useRef } from "react";

import { APIKeysCard } from "./components/api-keys-card";
import { ConfigCard } from "./components/config-card";
import { CPAPoolDialog } from "./components/cpa-pool-dialog";
import { CPAPoolsCard } from "./components/cpa-pools-card";
import { DataStorageCard } from "./components/data-storage-card";
import { ImageRuntimeCard } from "./components/image-runtime-card";
import { ImportBrowserDialog } from "./components/import-browser-dialog";
import { MaintenanceCard } from "./components/maintenance-card";
import { SettingsHeader } from "./components/settings-header";
import { Sub2APIConnections } from "./components/sub2api-connections";
import { useSettingsStore } from "./store";
import { IMPORT_PROGRESS_POLL_INTERVAL_MS } from "@/lib/polling";

function SettingsDataController() {
  const didLoadRef = useRef(false);
  const pollInFlightRef = useRef(false);
  const initialize = useSettingsStore((state) => state.initialize);
  const loadPools = useSettingsStore((state) => state.loadPools);
  const pools = useSettingsStore((state) => state.pools);
  const hasRunningJobs = useMemo(
    () =>
      pools.some((pool) => {
        const status = pool.import_job?.status;
        return status === "pending" || status === "running";
      }),
    [pools],
  );

  useEffect(() => {
    if (didLoadRef.current) {
      return;
    }
    didLoadRef.current = true;
    void initialize();
  }, [initialize]);

  useEffect(() => {
    if (!hasRunningJobs) {
      return;
    }

    const timer = window.setInterval(() => {
      if (pollInFlightRef.current) {
        return;
      }
      pollInFlightRef.current = true;
      void loadPools(true).finally(() => {
        pollInFlightRef.current = false;
      });
    }, IMPORT_PROGRESS_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [hasRunningJobs, loadPools]);

  return null;
}

export default function SettingsPage() {
  return (
    <>
      <SettingsDataController />
      <SettingsHeader />
      <section className="space-y-6">
        <ConfigCard />
        <ImageRuntimeCard />
        <DataStorageCard />
        <MaintenanceCard />
        <APIKeysCard />
        <CPAPoolsCard />
        <Sub2APIConnections />
      </section>
      <CPAPoolDialog />
      <ImportBrowserDialog />
    </>
  );
}
