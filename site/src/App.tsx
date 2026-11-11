import { Architecture } from "./components/Architecture";
import { Faq } from "./components/Faq";
import { Features } from "./components/Features";
import { Footer } from "./components/Footer";
import { Hero } from "./components/Hero";
import { Navbar } from "./components/Navbar";
import { Overview } from "./components/Overview";
import { PresentationSection } from "./components/PresentationSection";
import { Screenshots } from "./components/Screenshots";
import { Security } from "./components/Security";
import { SetupGuide } from "./components/SetupGuide";
import { TechStack } from "./components/TechStack";
import { VerifiedScope } from "./components/VerifiedScope";

export default function App() {
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Navbar />
      <main id="main" tabIndex={-1} className="focus:outline-none">
        <Hero />
        <Overview />
        <Features />
        <Architecture />
        <TechStack />
        <SetupGuide />
        <Security />
        <PresentationSection />
        <VerifiedScope />
        <Screenshots />
        <Faq />
      </main>
      <Footer />
    </>
  );
}
