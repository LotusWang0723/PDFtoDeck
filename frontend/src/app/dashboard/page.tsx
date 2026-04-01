'use client'

import { useSession } from "next-auth/react"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"

interface UserProfile {
  id: string
  email: string
  name: string
  avatar_url: string
  credits: number
  daily_free_used: number
  daily_free_remaining: number
  tier: string
  created_at: string
  limits: {
    daily_converts: number
    max_pages: number
    max_file_size_mb: number
  }
  stats: {
    total_conversions: number
    total_pages: number
  }
}

interface Conversion {
  id: string
  filename: string
  pages: number
  status: string
  cost_credits: number
  created_at: string
  download_url: string
}

const PACKAGES = [
  { id: "starter", label: "Starter", credits: 5, price: "$1.99", pricePerCredit: "$0.40" },
  { id: "standard", label: "Standard", credits: 30, price: "$4.99", pricePerCredit: "$0.17", popular: true },
  { id: "pro", label: "Pro", credits: 100, price: "$9.99", pricePerCredit: "$0.10" },
]

export default function Dashboard() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [history, setHistory] = useState<Conversion[]>([])
  const [loading, setLoading] = useState(true)
  const [purchasing, setPurchasing] = useState<string | null>(null)

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/")
      return
    }
    if (session?.user?.email) {
      loadData()
    }
  }, [session, status])

  async function loadData() {
    try {
      const email = session!.user!.email!

      await fetch("/api/user/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          name: session!.user!.name,
          avatar_url: session!.user!.image,
        }),
      })

      const profileRes = await fetch(`/api/user/me?email=${encodeURIComponent(email)}`)
      if (profileRes.ok) {
        setProfile(await profileRes.json())
      }

      const historyRes = await fetch(`/api/user/history?email=${encodeURIComponent(email)}`)
      if (historyRes.ok) {
        const data = await historyRes.json()
        setHistory(data.history || [])
      }
    } catch (e) {
      console.error("Failed to load data", e)
    } finally {
      setLoading(false)
    }
  }

  async function handleBuyCredits(packageId: string) {
    if (!session?.user?.email || purchasing) return
    setPurchasing(packageId)

    try {
      const res = await fetch("/api/paypal/create-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ package: packageId, email: session.user.email }),
      })
      const data = await res.json()

      if (!res.ok) {
        alert(data.detail || "Failed to create order")
        setPurchasing(null)
        return
      }

      // Redirect to PayPal approval URL
      if (data.approve_url) {
        window.location.href = data.approve_url
      } else {
        alert("No approval URL received")
        setPurchasing(null)
      }
    } catch (e: any) {
      alert(e.message || "Failed to start payment")
      setPurchasing(null)
    }
  }

  // Handle return from PayPal
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get("token")
    const paymentStatus = params.get("payment")

    if (paymentStatus === "success" && token && session?.user?.email) {
      capturePayment(token)
    } else if (paymentStatus === "cancelled") {
      alert("Payment cancelled")
      window.history.replaceState({}, "", "/dashboard")
    }
  }, [session])

  async function capturePayment(orderId: string) {
    try {
      const res = await fetch("/api/paypal/capture-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order_id: orderId, email: session!.user!.email }),
      })
      const data = await res.json()

      if (res.ok) {
        alert(data.message || "Payment successful!")
        window.history.replaceState({}, "", "/dashboard")
        loadData()
      } else {
        alert("Payment failed: " + (data.detail || "Unknown error"))
      }
    } catch (e: any) {
      alert("Payment verification failed: " + e.message)
    }
  }

  if (status === "loading" || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400" />
      </div>
    )
  }

  if (!profile) return null

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <a href="/" className="text-indigo-400 hover:text-indigo-300 flex items-center gap-2">
            ← Back to PDFtoDeck
          </a>
          <h1 className="text-2xl font-bold">Dashboard</h1>
        </div>

        {/* Top Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {/* Profile Card */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <div className="flex items-center gap-4 mb-4">
              {profile.avatar_url ? (
                <img src={profile.avatar_url} alt="" className="w-14 h-14 rounded-full" />
              ) : (
                <div className="w-14 h-14 rounded-full bg-indigo-500/20 flex items-center justify-center text-xl">
                  {profile.name?.[0] || "?"}
                </div>
              )}
              <div>
                <h2 className="text-lg font-semibold">{profile.name}</h2>
                <p className="text-sm text-gray-400">{profile.email}</p>
              </div>
            </div>
            <div className="text-xs text-gray-500">
              Member since {new Date(profile.created_at).toLocaleDateString()}
            </div>
            <div className={`mt-3 inline-block px-2 py-1 rounded text-xs font-medium ${
              profile.tier === 'paid' ? 'bg-amber-500/20 text-amber-400' : 'bg-gray-700 text-gray-300'
            }`}>
              {profile.tier === "paid" ? "⭐ Paid" : "Free"}
            </div>
          </div>

          {/* Credits Card */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-sm text-gray-400 mb-2">Credits</h3>
            <div className="text-4xl font-bold text-indigo-400 mb-2">
              {profile.credits}
            </div>
            <div className="text-sm text-gray-400 mb-1">
              Free today: {profile.daily_free_remaining} / {profile.limits.daily_converts} remaining
            </div>
            <div className="text-xs text-gray-500">
              Max {profile.limits.max_pages} pages · {profile.limits.max_file_size_mb}MB per file
            </div>
          </div>

          {/* Stats Card */}
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <h3 className="text-sm text-gray-400 mb-2">Usage Stats</h3>
            <div className="space-y-3">
              <div>
                <div className="text-2xl font-bold">{profile.stats.total_conversions}</div>
                <div className="text-sm text-gray-400">Total conversions</div>
              </div>
              <div>
                <div className="text-2xl font-bold">{profile.stats.total_pages}</div>
                <div className="text-sm text-gray-400">Total pages converted</div>
              </div>
            </div>
          </div>
        </div>

        {/* Buy Credits */}
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4">Buy Credits</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {PACKAGES.map((pkg) => (
              <div
                key={pkg.id}
                className={`relative bg-gray-900 rounded-xl p-6 border transition hover:border-indigo-500 ${
                  pkg.popular ? "border-indigo-500" : "border-gray-800"
                }`}
              >
                {pkg.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-indigo-500 rounded-full text-xs font-medium">
                    Most Popular
                  </div>
                )}
                <div className="text-lg font-semibold mb-1">{pkg.label}</div>
                <div className="text-3xl font-bold mb-1">{pkg.price}</div>
                <div className="text-sm text-gray-400 mb-4">
                  {pkg.credits} credits · {pkg.pricePerCredit}/credit
                </div>
                <button 
                  onClick={() => handleBuyCredits(pkg.id)}
                  disabled={purchasing !== null}
                  className={`w-full py-2.5 rounded-lg font-medium transition ${
                    pkg.popular
                      ? "bg-indigo-500 hover:bg-indigo-600 text-white"
                      : "bg-gray-800 hover:bg-gray-700 text-gray-300"
                  } ${purchasing === pkg.id ? "opacity-50 cursor-wait" : ""} disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {purchasing === pkg.id ? "Processing..." : `Buy ${pkg.credits} Credits`}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Conversion History */}
        <div>
          <h2 className="text-xl font-bold mb-4">Conversion History</h2>
          {history.length === 0 ? (
            <div className="bg-gray-900 rounded-xl p-8 border border-gray-800 text-center text-gray-400">
              No conversions yet. <a href="/" className="text-indigo-400 hover:underline">Convert your first PDF →</a>
            </div>
          ) : (
            <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-800 text-sm text-gray-400">
                    <th className="text-left p-4">File</th>
                    <th className="text-left p-4">Pages</th>
                    <th className="text-left p-4">Status</th>
                    <th className="text-left p-4">Credits</th>
                    <th className="text-left p-4">Date</th>
                    <th className="text-left p-4"></th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((conv) => (
                    <tr key={conv.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                      <td className="p-4 text-sm">{conv.filename || "—"}</td>
                      <td className="p-4 text-sm text-gray-400">{conv.pages}</td>
                      <td className="p-4">
                        <span className={`text-xs px-2 py-1 rounded-full ${
                          conv.status === "done" ? "bg-green-500/20 text-green-400"
                            : conv.status === "error" ? "bg-red-500/20 text-red-400"
                            : "bg-yellow-500/20 text-yellow-400"
                        }`}>
                          {conv.status}
                        </span>
                      </td>
                      <td className="p-4 text-sm text-gray-400">
                        {conv.cost_credits > 0 ? `-${conv.cost_credits}` : "Free"}
                      </td>
                      <td className="p-4 text-sm text-gray-400">
                        {new Date(conv.created_at).toLocaleDateString()}
                      </td>
                      <td className="p-4">
                        {conv.status === "done" && conv.download_url && (
                          <a href={conv.download_url} className="text-indigo-400 hover:text-indigo-300 text-sm">
                            Download
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </main>
  )
}
