import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Farm Harvest Annotation Tool",
  description: "Annotate farm harvest images",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
