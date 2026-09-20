import Foundation

struct HelpAlert: Codable {
    let event_id: String
    let server_session: String
    let source: String
    let timestamp: String
    let test_mode: Bool
    let latitude: Double?
    let longitude: Double?
    let accuracy: Double?
    let location_timestamp: String?
}

struct PendingAlert: Codable {
    let baseURL: String
    let alert: HelpAlert
}

struct ServerStatus: Decodable {
    let `protocol`: Int
    let server_session: String
    let auto_dispatch: Bool
}

struct AlertReceipt: Decodable {
    let event_id: String
    let status: String
    let message: String
}

struct WatchError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

enum ServerAddress {
    static func parse(_ input: String) throws -> URL {
        guard let parts = URLComponents(string: input.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = parts.scheme?.lowercased(), ["http", "https"].contains(scheme),
              let host = parts.host?.lowercased(), !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/", let url = parts.url else {
            throw WatchError(message: "Use a server origin, such as http://192.168.1.50:8000")
        }
        guard host != "localhost", host != "::1", host != "[::1]", host != "0.0.0.0",
              !host.hasPrefix("127.") else {
            throw WatchError(message: "Use the Mac's LAN address. Localhost means this Watch.")
        }
        let octets = host.split(separator: ".").compactMap { Int($0) }
        let privateIPv4 = host.split(separator: ".", omittingEmptySubsequences: false).count == 4
            && octets.count == 4 && octets.allSatisfy { (0...255).contains($0) }
            && (octets[0] == 10 || (octets[0] == 192 && octets[1] == 168)
                || (octets[0] == 172 && (16...31).contains(octets[1])))
        guard scheme == "https" || privateIPv4 || host.hasSuffix(".local") else {
            throw WatchError(message: "HTTP is limited to private LAN addresses or .local names.")
        }
        return url
    }
}

final class NoRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

enum WatchHTTP {
    static func request<T: Decodable>(_ base: URL, path: String, body: Data? = nil) async throws -> T {
        var request = URLRequest(url: base.appendingPathComponent(path))
        request.httpMethod = body == nil ? "GET" : "POST"
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForResource = 12
        config.waitsForConnectivity = false
        let session = URLSession(configuration: config, delegate: NoRedirects(), delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw WatchError(message: "No server response")
        }
        guard (200...299).contains(http.statusCode) else {
            let detail = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let message = (detail?["detail"] as? String) ?? "Request rejected"
            throw WatchError(message: "Server \(http.statusCode): \(message)")
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
