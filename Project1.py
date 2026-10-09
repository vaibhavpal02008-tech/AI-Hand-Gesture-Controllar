from server_backend import app, generate_password


def main() -> None:
	import sys

	if "--cli" in sys.argv[1:]:
		print("=====================================")
		print("    PASSWORD GENERATOR   ")
		print("=====================================")
		try:
			length = int(input("Enter password length: "))
			print(f"Generated password: {generate_password(length)}")
		except ValueError as error:
			print(f"Error: {error}")
		return

	print("Commonplace is running at http://127.0.0.1:5000")
	print("Press Ctrl+C to stop the server.")
	app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
	main()