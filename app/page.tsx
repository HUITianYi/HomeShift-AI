import type { Metadata } from "next";
import HomeShiftApp from "./components/HomeShiftApp";

export const metadata: Metadata = {
  title: "HomeShift AI — Cut bills, not comfort",
  description:
    "An agentic household energy copilot that turns real usage data into explainable, adaptive savings plans.",
};

export default function Home() {
  return <HomeShiftApp />;
}
